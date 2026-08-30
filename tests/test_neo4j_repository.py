from __future__ import annotations

from easysql.repositories.neo4j_repository import Neo4jRepository


class FakeDriver:
    def __init__(self) -> None:
        self.verify_calls = 0

    def verify_connectivity(self) -> None:
        self.verify_calls += 1


def test_existing_driver_is_returned_without_connectivity_probe() -> None:
    repository = Neo4jRepository(
        uri="bolt://example:7687",
        user="neo4j",
        password="secret",
    )
    driver = FakeDriver()
    repository._driver = driver  # type: ignore[assignment]

    assert repository.driver is driver
    assert driver.verify_calls == 0
