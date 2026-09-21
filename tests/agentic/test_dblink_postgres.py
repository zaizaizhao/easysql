from __future__ import annotations

from sqlalchemy import text

from easysql.federation import DatabaseScope, FederatedSqlExecutor
from easysql.infrastructure.data_plane_engine_registry import DataPlaneEngineRegistry
from easysql_agentic.tools.sql import validate_submission


def test_real_three_database_dblink_and_remote_errors(federated_settings) -> None:
    scope = DatabaseScope.resolve(federated_settings, db_names=["emr", "pms", "rvs"])
    registry = DataPlaneEngineRegistry()
    executor = FederatedSqlExecutor(settings=federated_settings, registry=registry)
    sql = """SELECT e.mpi_id, p.amount + r.amount AS total
    FROM public.patient e
    JOIN dblink('pms_conn', $$SELECT mpi_id,amount FROM public.patient$$)
      AS p(mpi_id text,amount integer) ON e.mpi_id=p.mpi_id
    JOIN dblink('rvs_conn', $$SELECT mpi_id,amount FROM public.patient$$)
      AS r(mpi_id text,amount integer) ON e.mpi_id=r.mpi_id"""
    try:
        parsed, error = validate_submission(sql, scope, "emr", executor)
        assert error is None
        assert parsed.tables == ["emr.public.patient", "pms.public.patient", "rvs.public.patient"]
        _, remote_error = validate_submission(
            sql.replace("SELECT mpi_id,amount", "SELECT missing_column,amount", 1),
            scope,
            "emr",
            executor,
        )
        assert remote_error is not None
        assert "missing_column" in remote_error
        _, hidden_error = validate_submission(
            sql.replace("SELECT mpi_id,amount", "SELECT missing_column,amount", 1)
            + " WHERE e.id < 0",
            scope,
            "emr",
            executor,
        )
        assert hidden_error and "missing_column" in hidden_error
        with registry.get_engine(scope.require_primary("emr").config).connect() as connection:
            assert not connection.execute(text("SELECT dblink_get_connections()")).scalar_one()
    finally:
        registry.dispose_all()
