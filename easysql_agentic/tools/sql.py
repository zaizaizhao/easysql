"""Parse both local and remote SQL, then reuse the existing dblink executor."""

from __future__ import annotations

from dataclasses import dataclass

import sqlglot
from sqlglot import exp
from sqlglot.optimizer.normalize_identifiers import normalize_identifiers
from sqlglot.optimizer.scope import build_scope

from easysql.federation import DatabaseScope, FederatedSqlExecutor, FederatedSqlRequest

FORBIDDEN_FUNCTIONS = {
    "dblink_connect",
    "dblink_connect_u",
    "dblink_disconnect",
    "dblink_exec",
    "dblink_send_query",
    "dblink_open",
    "dblink_close",
    "set_config",
    "setval",
    "nextval",
    "pg_read_file",
    "pg_write_file",
    "pg_terminate_backend",
    "lo_import",
    "lo_export",
    "pg_advisory_lock",
}


@dataclass
class ParsedSql:
    sql: str
    validation_sql: str
    tables: list[str]
    remote_queries: list[tuple[str, str]]


def parse_read_query(sql: str, scope: DatabaseScope, primary_db: str) -> ParsedSql:
    primary = scope.require_primary(primary_db)
    primary_db = primary.name
    dialect = {"postgresql": "postgres", "sqlserver": "tsql"}.get(
        primary.config.db_type, primary.config.db_type
    )
    tables: set[str] = set()
    remote_queries: list[tuple[str, str]] = []

    def inspect_query(source: str, database: str, *, remote: bool = False) -> exp.Query:
        statements = sqlglot.parse(source, read=dialect)
        if len(statements) != 1 or not isinstance(statements[0], exp.Query):
            raise ValueError("Only one read-only SELECT/WITH query is allowed")
        tree = normalize_identifiers(statements[0], dialect=dialect)
        if any(isinstance(node, (exp.DDL, exp.DML, exp.Into, exp.Lock)) for node in tree.walk()):
            raise ValueError("Mutations, SELECT INTO and locking reads are not allowed")
        default_schema = scope.require_primary(database).schema
        root = build_scope(tree)
        physical_tables = (
            [
                source
                for query_scope in root.traverse()
                for _, source in query_scope.selected_sources.values()
                if isinstance(source, exp.Table)
            ]
            if root
            else []
        )
        for table in physical_tables:
            if not isinstance(table.this, exp.Identifier):
                continue
            if table.catalog:
                raise ValueError("Logical database aliases cannot be used as SQL catalog prefixes")
            schema = table.db or default_schema
            if schema != default_schema:
                raise ValueError(f"Schema {schema!r} is outside configured database {database!r}")
            if not table.db:
                table.set("db", exp.to_identifier(default_schema, quoted=True))
            tables.add(f"{database}.{schema}.{table.name}")
        for function in tree.find_all(exp.Func):
            name = (
                function.name if isinstance(function, exp.Anonymous) else function.sql_name()
            ).lower()
            if name in FORBIDDEN_FUNCTIONS or name.startswith("dblink_"):
                raise ValueError(
                    "Connection management and side-effect functions are not SQL tools"
                )
            if name == "dblink":
                if remote or not scope.is_federated:
                    raise ValueError(
                        "Nested dblink or dblink outside a multi-database scope is forbidden"
                    )
                args = function.expressions
                if len(args) != 2 or any(
                    not (
                        isinstance(arg, exp.RawString)
                        or isinstance(arg, exp.Literal)
                        and arg.is_string
                    )
                    for arg in args
                ):
                    raise ValueError(
                        "dblink requires a configured connection name and literal remote SELECT"
                    )
                target = scope.target_for_connection(args[0].this)
                if target is None or target.name == primary_db:
                    raise ValueError(
                        "The dblink connection is outside the selected remote databases"
                    )
                remote_query = inspect_query(args[1].this, target.name, remote=True)
                remote_sql = remote_query.sql(dialect=dialect)
                remote_queries.append((target.name, remote_sql))
                args[1].replace(exp.Literal.string(remote_sql))
        return tree

    tree = inspect_query(sql, primary_db)
    return ParsedSql(
        sql=tree.sql(dialect=dialect),
        validation_sql=tree.copy().limit(1).sql(dialect=dialect),
        tables=sorted(tables),
        remote_queries=list(dict.fromkeys(remote_queries)),
    )


def validate_submission(
    sql: str,
    scope: DatabaseScope,
    primary_db: str,
    executor: FederatedSqlExecutor,
    timeout_seconds: int = 20,
) -> tuple[ParsedSql, str | None]:
    parsed = parse_read_query(sql, scope, primary_db)
    # A LIMIT 1 outer execution may short-circuit an empty join and never invoke
    # dblink. Plan every remote SELECT independently before validating the join.
    for database, remote_sql in parsed.remote_queries:
        remote = executor.validate(
            FederatedSqlRequest(
                sql=remote_sql,
                primary_db=database,
                db_names=(database,),
                timeout_seconds=timeout_seconds,
                read_only=True,
            )
        )
        if not remote.success:
            return parsed, remote.error or f"Remote SQL validation failed on {database}"
    result = executor.execute(
        FederatedSqlRequest(
            sql=parsed.validation_sql,
            primary_db=primary_db,
            db_names=tuple(scope.names),
            timeout_seconds=timeout_seconds,
            read_only=True,
        )
    )
    return parsed, None if result.success else result.error or "SQL validation failed"
