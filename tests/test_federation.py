from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest
from psycopg2.extensions import parse_dsn

from easysql.config import DatabaseConfig, Settings
from easysql.federation import (
    DatabaseScope,
    FederatedSqlExecutor,
    FederatedSqlRequest,
    FederationStatusProbe,
)


def _db(name: str, db_type: str = "postgresql") -> DatabaseConfig:
    return DatabaseConfig(
        name=name,
        db_type=db_type,
        host="localhost",
        port=5432,
        user="app",
        password="secret",
        database=f"{name}_physical",
        schema="public",
        system_type=name.upper(),
    )


def _settings(*databases: DatabaseConfig) -> Settings:
    return Settings(
        _env_file=None,
        databases={database.name.lower(): database for database in databases},
    )


class FakeRow:
    def __init__(self, values: dict[str, Any]):
        self._mapping = values


class FakeResult:
    def __init__(
        self,
        *,
        rows: list[dict[str, Any]] | None = None,
        scalar: Any = None,
        row: tuple[Any, ...] | None = None,
    ) -> None:
        self._rows = rows or []
        self._scalar = scalar
        self._row = row
        self.returns_rows = rows is not None
        self.rowcount = len(self._rows)

    def __iter__(self):
        return iter(FakeRow(row) for row in self._rows)

    def keys(self) -> list[str]:
        return list(self._rows[0]) if self._rows else []

    def scalar_one(self) -> Any:
        return self._scalar

    def one(self) -> tuple[Any, ...]:
        if self._row is None:
            raise AssertionError("FakeResult has no tuple row")
        return self._row


class FakeConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any] | None]] = []

    def __enter__(self) -> FakeConnection:
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def execute(self, statement: Any, params: dict[str, Any] | None = None) -> FakeResult:
        sql = str(statement)
        self.calls.append((sql, params))
        if "dblink_get_connections" in sql:
            return FakeResult(scalar=[])
        if "dblink_connect" in sql:
            return FakeResult(scalar="OK")
        if "dblink_disconnect" in sql:
            return FakeResult(scalar="OK")
        if "FROM pg_database" in sql:
            return FakeResult(scalar=True)
        if "inet_server_addr" in sql:
            return FakeResult(row=("10.0.0.10", 5432))
        if "set_config" in sql:
            return FakeResult(scalar="30000ms")
        if sql.startswith("EXPLAIN"):
            return FakeResult(rows=[{"QUERY PLAN": "plan"}])
        return FakeResult(rows=[{"patient_id": 1}])


@dataclass
class FakeEngine:
    connection: FakeConnection

    def connect(self) -> FakeConnection:
        return self.connection


class FakeRegistry:
    def __init__(self) -> None:
        self.connection = FakeConnection()

    def get_engine(self, _config: DatabaseConfig) -> FakeEngine:
        return FakeEngine(self.connection)


def test_database_scope_keeps_single_non_postgres_compatible() -> None:
    scope = DatabaseScope.resolve(_settings(_db("his", "mysql")), db_names=["his"])

    assert scope.names == ["his"]
    assert scope.is_federated is False


def test_database_scope_requires_postgres_for_multiple_databases() -> None:
    with pytest.raises(ValueError, match="require PostgreSQL"):
        DatabaseScope.resolve(
            _settings(_db("emr"), _db("legacy", "mysql")),
            db_names=["emr", "legacy"],
        )


def test_prompt_context_contains_no_credentials() -> None:
    scope = DatabaseScope.resolve(
        _settings(_db("emr"), _db("pms")),
        db_names=["emr", "pms"],
    )

    prompt = scope.render_prompt_context()

    assert "emr_conn" in prompt
    assert "pms_conn" in prompt
    assert "foreign server" not in prompt.lower()
    assert "secret" not in prompt
    assert "password" in prompt


def test_federated_executor_opens_only_referenced_remote_connection() -> None:
    registry = FakeRegistry()
    executor = FederatedSqlExecutor(
        settings=_settings(_db("emr"), _db("pms"), _db("rvs")),
        registry=registry,
    )
    sql = """
    SELECT e.patient_id
    FROM public.patient e
    JOIN dblink('pms_conn', $$SELECT patient_id FROM public.patient$$)
      AS p(patient_id bigint) ON p.patient_id = e.patient_id
    """

    result = executor.execute(
        FederatedSqlRequest(
            sql=sql,
            primary_db="emr",
            db_names=("emr", "pms", "rvs"),
        )
    )

    assert result.success is True
    connect_calls = [call for call in registry.connection.calls if "dblink_connect" in call[0]]
    assert len(connect_calls) == 1
    params = connect_calls[0][1] or {}
    assert params["connection_name"] == "pms_conn"
    dsn = parse_dsn(params["conninfo"])
    assert dsn["host"] == "10.0.0.10"
    assert dsn["port"] == "5432"
    assert dsn["dbname"] == "pms_physical"
    assert dsn["user"] == "app"
    assert dsn["password"] == "secret"
    assert any("dblink_disconnect" in sql for sql, _ in registry.connection.calls)


def test_single_database_execution_never_invokes_dblink() -> None:
    registry = FakeRegistry()
    executor = FederatedSqlExecutor(
        settings=_settings(_db("emr")),
        registry=registry,
    )

    result = executor.execute(
        FederatedSqlRequest(
            sql="SELECT patient_id FROM public.patient",
            primary_db="emr",
            db_names=("emr",),
        )
    )

    assert result.success is True
    assert not any("dblink" in sql.lower() for sql, _ in registry.connection.calls)


def test_dblink_connection_failure_never_returns_password() -> None:
    class FailingConnection(FakeConnection):
        def execute(self, statement: Any, params: dict[str, Any] | None = None) -> FakeResult:
            sql = str(statement)
            if "dblink_connect" in sql:
                raise RuntimeError(f"driver parameters: {params}")
            return super().execute(statement, params)

    class FailingRegistry:
        def __init__(self) -> None:
            self.connection = FailingConnection()

        def get_engine(self, _config: DatabaseConfig) -> FakeEngine:
            return FakeEngine(self.connection)

    executor = FederatedSqlExecutor(
        settings=_settings(_db("emr"), _db("pms")),
        registry=FailingRegistry(),
    )

    result = executor.execute(
        FederatedSqlRequest(
            sql="SELECT * FROM dblink('pms_conn', $$SELECT 1$$) AS p(value int)",
            primary_db="emr",
            db_names=("emr", "pms"),
        )
    )

    assert result.success is False
    assert "secret" not in (result.error or "")
    assert "Cannot open dblink connection" in (result.error or "")


def test_federated_executor_rejects_unselected_connection_name() -> None:
    executor = FederatedSqlExecutor(
        settings=_settings(_db("emr"), _db("pms")),
        registry=FakeRegistry(),
    )

    result = executor.execute(
        FederatedSqlRequest(
            sql="SELECT * FROM dblink('rvs_conn', $$SELECT 1$$) AS x(value int)",
            primary_db="emr",
            db_names=("emr", "pms"),
        )
    )

    assert result.success is False
    assert "outside the selected" in (result.error or "")


def test_remote_sql_semicolon_inside_dollar_quote_is_not_a_second_statement() -> None:
    executor = FederatedSqlExecutor(
        settings=_settings(_db("emr"), _db("pms")),
        registry=FakeRegistry(),
    )

    result = executor.execute(
        FederatedSqlRequest(
            sql=(
                "SELECT * FROM dblink('pms_conn', "
                "$$SELECT patient_id FROM public.patient;$$) AS p(patient_id bigint);"
            ),
            primary_db="emr",
            db_names=("emr", "pms"),
        )
    )

    assert result.success is True


def test_stacked_outer_statements_are_rejected() -> None:
    executor = FederatedSqlExecutor(
        settings=_settings(_db("emr"), _db("pms")),
        registry=FakeRegistry(),
    )

    result = executor.execute(
        FederatedSqlRequest(
            sql="SELECT 1; SELECT 2",
            primary_db="emr",
            db_names=("emr", "pms"),
        )
    )

    assert result.success is False
    assert "one SQL statement" in (result.error or "")


def test_mutation_inside_remote_dblink_sql_is_rejected() -> None:
    executor = FederatedSqlExecutor(
        settings=_settings(_db("emr"), _db("pms")),
        registry=FakeRegistry(),
    )

    result = executor.execute(
        FederatedSqlRequest(
            sql=(
                "SELECT * FROM dblink('pms_conn', "
                "$$DELETE FROM public.patient RETURNING patient_id$$) "
                "AS p(patient_id bigint)"
            ),
            primary_db="emr",
            db_names=("emr", "pms"),
        )
    )

    assert result.success is False
    assert "read-only" in (result.error or "")


def test_mutation_keyword_inside_string_literal_is_not_rejected() -> None:
    executor = FederatedSqlExecutor(
        settings=_settings(_db("emr"), _db("pms")),
        registry=FakeRegistry(),
    )

    result = executor.execute(
        FederatedSqlRequest(
            sql=(
                "SELECT * FROM dblink('pms_conn', "
                "$$SELECT mpi_id FROM public.consent_record "
                "WHERE consent_status NOT ILIKE '%revoke%'$$) "
                "AS p(mpi_id varchar)"
            ),
            primary_db="emr",
            db_names=("emr", "pms"),
        )
    )

    assert result.success is True


def test_federated_validation_uses_explain_without_analyze() -> None:
    registry = FakeRegistry()
    executor = FederatedSqlExecutor(
        settings=_settings(_db("emr"), _db("pms")),
        registry=registry,
    )

    result = executor.validate(
        FederatedSqlRequest(
            sql="SELECT 1",
            primary_db="emr",
            db_names=("emr", "pms"),
        )
    )

    assert result.success is True
    explain_sql = next(sql for sql, _ in registry.connection.calls if sql.startswith("EXPLAIN"))
    assert explain_sql.startswith("EXPLAIN SELECT")
    assert "ANALYZE" not in explain_sql


class StatusFakeConnection:
    def __init__(self, *, extension_installed: bool = True) -> None:
        self.extension_installed = extension_installed
        self.remote_databases: dict[str, str] = {}

    def __enter__(self) -> StatusFakeConnection:
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def execute(self, statement: Any, params: dict[str, Any] | None = None) -> FakeResult:
        sql = str(statement)
        if "FROM pg_extension" in sql:
            return FakeResult(scalar=self.extension_installed)
        if "has_function_privilege" in sql:
            return FakeResult(scalar=True)
        if "FROM pg_database" in sql:
            return FakeResult(scalar=True)
        if "inet_server_addr" in sql:
            return FakeResult(row=("10.0.0.20", 5432))
        if "dblink_get_connections" in sql:
            return FakeResult(scalar=list(self.remote_databases))
        if "dblink_connect" in sql:
            values = params or {}
            self.remote_databases[values["connection_name"]] = parse_dsn(values["conninfo"])[
                "dbname"
            ]
            return FakeResult(scalar="OK")
        if "dblink_disconnect" in sql:
            values = params or {}
            self.remote_databases.pop(values["connection_name"], None)
            return FakeResult(scalar="OK")
        if "AS probe(remote_database text)" in sql:
            values = params or {}
            return FakeResult(scalar=self.remote_databases[values["connection_name"]])
        if "set_config" in sql:
            return FakeResult(scalar="5000ms")
        raise AssertionError(f"Unexpected SQL: {sql}")


class StatusFakeRegistry:
    def __init__(self, *, extension_installed: bool = True) -> None:
        self.extension_installed = extension_installed
        self.connections: dict[str, StatusFakeConnection] = {}

    def get_engine(self, config: DatabaseConfig) -> FakeEngine:
        connection = StatusFakeConnection(extension_installed=self.extension_installed)
        self.connections[config.name] = connection
        return FakeEngine(connection)


def test_federation_status_explicitly_marks_single_database_without_dblink() -> None:
    probe = FederationStatusProbe(registry=StatusFakeRegistry())

    status = probe.check(_settings(_db("emr")), ["emr"])

    assert status.mode == "single"
    assert status.status == "not_required"
    assert status.reason == "single_database"
    assert status.databases[0].extension_installed is None


def test_federation_status_checks_every_dblink_direction() -> None:
    registry = StatusFakeRegistry()
    probe = FederationStatusProbe(registry=registry)

    status = probe.check(_settings(_db("emr"), _db("pms"), _db("rvs")), ["emr", "pms", "rvs"])

    assert status.mode == "dblink"
    assert status.status == "ready"
    assert len(status.databases) == 3
    assert sum(len(database.routes) for database in status.databases) == 6
    assert all(database.status == "ready" for database in status.databases)
    assert all(not connection.remote_databases for connection in registry.connections.values())


def test_federation_status_reports_missing_extension_per_primary() -> None:
    probe = FederationStatusProbe(registry=StatusFakeRegistry(extension_installed=False))

    status = probe.check(_settings(_db("emr"), _db("pms")), ["emr", "pms"])

    assert status.status == "unavailable"
    assert status.reason == "extension_missing"
    assert all(database.reason == "extension_missing" for database in status.databases)
