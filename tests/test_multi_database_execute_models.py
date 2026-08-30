from easysql_api.models.execute import ExecuteRequest
from easysql_api.services.execute_service import ExecuteService


def test_execute_request_normalizes_legacy_single_database() -> None:
    request = ExecuteRequest(sql="SELECT 1", db_name="emr")

    assert request.db_names == ["emr"]
    assert request.primary_db == "emr"


def test_execute_request_accepts_multi_database_primary() -> None:
    request = ExecuteRequest(
        sql="SELECT 1",
        db_names=["emr", "pms"],
        primary_db="pms",
    )

    assert request.db_name == "pms"
    assert request.db_names == ["emr", "pms"]


def test_with_query_is_classified_as_select_and_gets_limit() -> None:
    service = ExecuteService()
    sql = "WITH patients AS (SELECT patient_id FROM patient) SELECT * FROM patients"

    check = service.check_sql(sql)

    assert check.statement_type == "SELECT"
    assert service._apply_limit(sql, 101).endswith("LIMIT 101")
