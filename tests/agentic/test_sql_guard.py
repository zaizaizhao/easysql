from __future__ import annotations

import pytest

from easysql.config import DatabaseConfig, Settings
from easysql.federation import DatabaseScope
from easysql_agentic.tools.sql import parse_read_query


@pytest.fixture
def scope():
    config = Settings(
        _env_file=None,
        databases={
            name: DatabaseConfig(
                name=name,
                db_type="postgresql",
                host="localhost",
                port=5432,
                user="test",
                password="test",
                database=name,
            )
            for name in ["emr", "pms", "rvs"]
        },
    )
    return DatabaseScope.resolve(config, db_names=["emr", "pms", "rvs"])


def test_three_database_query_and_dollar_quoted_remote_queries(scope) -> None:
    sql = """SELECT e.id FROM public.patient e
    JOIN dblink('pms_conn', $$SELECT id FROM public.account LIMIT 20$$) AS p(id bigint) ON p.id=e.id
    JOIN dblink('rvs_conn', 'SELECT id FROM public.course') AS r(id bigint) ON r.id=e.id"""
    result = parse_read_query(sql, scope, "emr")
    assert result.tables == ["emr.public.patient", "pms.public.account", "rvs.public.course"]
    assert result.validation_sql.endswith("LIMIT 1")
    assert "LIMIT 20" in result.validation_sql


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM dblink('rvs_conn', 'DELETE FROM public.course RETURNING id') AS r(id bigint)",
        "WITH x AS (DELETE FROM public.patient RETURNING id) SELECT * FROM x",
        "SELECT * INTO changed FROM public.patient",
        "SELECT * FROM public.patient; DELETE FROM public.patient",
        "SELECT * FROM dblink('outside_conn','SELECT id FROM public.patient') AS r(id bigint)",
        "SELECT * FROM dblink('rvs_conn','SELECT id FROM public.course',false) AS r(id bigint)",
        "SELECT set_config('transaction_read_only','off',false)",
        "SELECT * FROM private.patient",
        "SELECT * FROM emr.public.patient",
    ],
)
def test_rejects_remote_mutation_scope_escape_and_side_effects(scope, sql) -> None:
    with pytest.raises(ValueError):
        parse_read_query(sql, scope, "emr")


def test_cte_does_not_hide_qualified_real_table(scope) -> None:
    result = parse_read_query(
        "WITH patient AS (SELECT id FROM public.patient) SELECT * FROM patient", scope, "emr"
    )
    assert result.tables == ["emr.public.patient"]


def test_cte_shadowing_still_requires_the_underlying_schema(scope) -> None:
    result = parse_read_query(
        "WITH patient AS (SELECT id FROM patient) SELECT * FROM patient", scope, "EMR"
    )
    assert result.tables == ["emr.public.patient"]


def test_postgresql_unquoted_identifiers_are_folded_but_quoted_names_are_preserved(scope) -> None:
    assert parse_read_query("SELECT ID FROM PUBLIC.PATIENT", scope, "emr").tables == [
        "emr.public.patient"
    ]
    assert parse_read_query('SELECT id FROM public."Patient"', scope, "emr").tables == [
        "emr.public.Patient"
    ]


def test_unqualified_local_and_remote_tables_use_the_configured_schema(scope) -> None:
    result = parse_read_query(
        "SELECT p.id FROM patient p JOIN dblink('rvs_conn', 'SELECT id FROM patient') AS r(id bigint) ON r.id=p.id",
        scope,
        "emr",
    )
    assert result.sql.count('"public".patient') == 2
    assert result.tables == ["emr.public.patient", "rvs.public.patient"]
