"""Resolve a user's selected logical databases into one validated query scope."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from easysql.config import DatabaseConfig, Settings


@dataclass(frozen=True)
class DatabaseTarget:
    """A configured logical database as exposed to retrieval and SQL generation."""

    name: str
    config: DatabaseConfig

    @property
    def schema(self) -> str:
        return self.config.get_default_schema()

    @property
    def dblink_server(self) -> str:
        return self.config.get_dblink_server()

    @property
    def dblink_connection_name(self) -> str:
        return self.config.get_dblink_connection_name()


@dataclass(frozen=True)
class DatabaseScope:
    """Selected data sources and the invariants required for one query.

    This is the seam shared by the API, retrieval, prompts, agent tools and SQL
    execution. Callers only need selected logical names; validation and dblink
    naming stay inside this module.
    """

    targets: tuple[DatabaseTarget, ...]

    @classmethod
    def resolve(
        cls,
        settings: Settings,
        *,
        db_names: list[str] | tuple[str, ...] | None = None,
        db_name: str | None = None,
    ) -> DatabaseScope:
        requested = list(db_names or [])
        if not requested and db_name:
            requested = [db_name]
        if not requested and settings.databases:
            requested = [next(iter(settings.databases))]
        if not requested:
            raise ValueError("No database is configured")

        normalized: list[str] = []
        for name in requested:
            key = str(name).strip().lower()
            if not key:
                continue
            if key not in normalized:
                normalized.append(key)

        missing = [name for name in normalized if name not in settings.databases]
        if missing:
            raise ValueError(f"Database(s) not configured: {', '.join(missing)}")

        targets = tuple(
            DatabaseTarget(name=name, config=settings.databases[name]) for name in normalized
        )
        if len(targets) > 1:
            non_postgres = [
                target.name for target in targets if target.config.db_type != "postgresql"
            ]
            if non_postgres:
                raise ValueError(
                    "Multi-database dblink queries require PostgreSQL for every selected "
                    f"database; incompatible: {', '.join(non_postgres)}"
                )

            connection_names = [target.dblink_connection_name for target in targets]
            duplicates = sorted(
                {name for name in connection_names if connection_names.count(name) > 1}
            )
            if duplicates:
                raise ValueError("dblink connection names must be unique: " + ", ".join(duplicates))

        return cls(targets=targets)

    @property
    def names(self) -> list[str]:
        return [target.name for target in self.targets]

    @property
    def is_federated(self) -> bool:
        return len(self.targets) > 1

    @property
    def default_primary(self) -> str:
        return self.targets[0].name

    def require_primary(self, primary_db: str | None) -> DatabaseTarget:
        key = (primary_db or self.default_primary).strip().lower()
        for target in self.targets:
            if target.name == key:
                return target
        raise ValueError(
            f"Primary database '{primary_db}' is not in selected databases: "
            + ", ".join(self.names)
        )

    def target_for_connection(self, connection_name: str) -> DatabaseTarget | None:
        for target in self.targets:
            if target.dblink_connection_name == connection_name:
                return target
        return None

    def render_prompt_context(self) -> str:
        """Render credential-free routing and dblink instructions for the LLM."""
        lines = ["## 数据库执行范围", ""]
        lines.append("本次允许使用的逻辑数据库：")
        for target in self.targets:
            description = target.config.description or target.config.system_type
            suffix = f" - {description}" if description and description != "UNKNOWN" else ""
            lines.append(
                f"- {target.name}: PostgreSQL schema={target.schema}{suffix}"
                if target.config.db_type == "postgresql"
                else f"- {target.name}: {target.config.db_type} schema={target.schema}{suffix}"
            )

        if not self.is_federated:
            lines.extend(
                [
                    "",
                    f"这是单库查询。primary_db 必须为 {self.default_primary}，使用普通 SQL，禁止使用 dblink。",
                ]
            )
            return "\n".join(lines)

        lines.extend(
            [
                "",
                "这是多库查询。你必须根据用户问题选择一个 primary_db 作为 SQL 执行库；",
                "primary_db 中的表直接使用 schema.table，其他所选库通过 dblink 查询。",
                "Schema 中显示的 db.schema.table 只用于区分元数据；实际本地或远端 SQL 都只写 schema.table，不要把逻辑库名前缀写进 PostgreSQL 表名。",
                "不要生成 dblink_connect/dblink_disconnect；执行器会使用配置页保存的数据库凭据，在同一数据库会话中自动建立并清理连接。",
                "dblink() 返回 record，AS 别名中必须显式写出每个返回列及准确 PostgreSQL 类型。",
                "只允许使用下面列出的连接名，禁止在 SQL 中放入 host、user、password 或连接串：",
            ]
        )
        for target in self.targets:
            lines.append(
                f"- 访问 {target.name}: dblink connection='{target.dblink_connection_name}'"
            )
        lines.extend(
            [
                "",
                "典型形式：",
                "SELECT ... FROM local_schema.local_table l",
                "JOIN dblink('remote_conn', $$SELECT id, value FROM remote_schema.remote_table$$)",
                "  AS r(id bigint, value text) ON r.id = l.id",
            ]
        )
        return "\n".join(lines)
