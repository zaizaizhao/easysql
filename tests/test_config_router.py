from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from easysql_api.deps import get_config_service_dep
from easysql_api.routers.config import router


class FakeConfigService:
    def __init__(self) -> None:
        self.last_update: tuple[str, dict, bool] | None = None
        self.last_delete: tuple[str, bool] | None = None

    async def get_editable_config(self):
        return {
            "llm": {
                "query_mode": {
                    "value": "plan",
                    "is_secret": False,
                    "is_overridden": False,
                    "nullable": False,
                    "value_type": "str",
                }
            }
        }

    async def get_overrides(self):
        return {"llm": {}}

    async def get_database_configs(self):
        return [
            {
                "name": "emr",
                "type": "postgresql",
                "host": "localhost",
                "port": 5432,
                "user": "app",
                "database": "emr",
                "schema": "public",
                "system_type": "EMR",
                "description": "EMR",
                "dblink_connection_name": "emr_conn",
                "has_password": True,
            }
        ]

    async def replace_database_configs(self, databases, *, warmup: bool = False):
        public = [
            {
                **item,
                "type": item.pop("db_type"),
                "schema": item.pop("schema_name", None) or "public",
                "system_type": item.get("system_type") or "UNKNOWN",
                "description": item.get("description") or "",
                "dblink_connection_name": f"{item['name']}_conn",
                "has_password": bool(item.pop("password", None)),
            }
            for item in [dict(database) for database in databases]
        ]
        return {"databases": public, "total": len(public), "updated": [d["name"] for d in public]}

    async def test_database_config(self, database):
        return f"Connected to {database['name']} successfully"

    async def get_database_federation_status(self, db_names):
        if len(db_names) == 1:
            return {
                "mode": "single",
                "status": "not_required",
                "reason": "single_database",
                "db_names": db_names,
                "databases": [
                    {
                        "name": db_names[0],
                        "connection_name": f"{db_names[0]}_conn",
                        "status": "not_required",
                        "reason": "single_database",
                        "extension_installed": None,
                        "connect_allowed": None,
                        "routes": [],
                    }
                ],
            }
        return {
            "mode": "dblink",
            "status": "ready",
            "reason": "ready",
            "db_names": db_names,
            "databases": [
                {
                    "name": name,
                    "connection_name": f"{name}_conn",
                    "status": "ready",
                    "reason": "ready",
                    "extension_installed": True,
                    "connect_allowed": True,
                    "routes": [
                        {
                            "source_db": name,
                            "target_db": target,
                            "status": "ready",
                            "reason": "ready",
                        }
                        for target in db_names
                        if target != name
                    ],
                }
                for name in db_names
            ],
        }

    async def update_category(self, category: str, updates: dict, *, warmup: bool = False):
        if category == "invalid":
            raise ValueError("bad category")
        self.last_update = (category, updates, warmup)
        return {
            "category": category,
            "updated": sorted(updates.keys()),
            "invalidate_tags": ["settings"],
        }

    async def delete_category(self, category: str, *, warmup: bool = False):
        if category == "invalid":
            raise ValueError("bad category")
        self.last_delete = (category, warmup)
        return {
            "category": category,
            "deleted": 2,
            "message": "Reverted to .env defaults",
            "invalidate_tags": ["settings"],
        }


def _create_client(service: FakeConfigService) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_config_service_dep] = lambda: service
    return TestClient(app)


def test_get_editable_config() -> None:
    service = FakeConfigService()
    client = _create_client(service)

    resp = client.get("/api/v1/config/editable")
    assert resp.status_code == 200
    assert resp.json()["llm"]["query_mode"]["value"] == "plan"


def test_patch_config_category() -> None:
    service = FakeConfigService()
    client = _create_client(service)

    resp = client.patch("/api/v1/config/llm", json={"query_mode": "fast"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["category"] == "llm"
    assert body["updated"] == ["query_mode"]
    assert service.last_update == ("llm", {"query_mode": "fast"}, True)


def test_put_config_category() -> None:
    service = FakeConfigService()
    client = _create_client(service)

    resp = client.put("/api/v1/config/llm", json={"query_mode": "fast"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["category"] == "llm"
    assert body["updated"] == ["query_mode"]
    assert service.last_update == ("llm", {"query_mode": "fast"}, True)


def test_patch_config_category_validation_error() -> None:
    service = FakeConfigService()
    client = _create_client(service)

    resp = client.patch("/api/v1/config/invalid", json={"query_mode": "fast"})
    assert resp.status_code == 422


def test_delete_config_category() -> None:
    service = FakeConfigService()
    client = _create_client(service)

    resp = client.delete("/api/v1/config/llm")
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 2
    assert service.last_delete == ("llm", True)


def test_get_database_configs_never_returns_password() -> None:
    service = FakeConfigService()
    client = _create_client(service)

    resp = client.get("/api/v1/config/databases")

    assert resp.status_code == 200
    body = resp.json()
    assert body["databases"][0]["name"] == "emr"
    assert body["databases"][0]["has_password"] is True
    assert "password" not in body["databases"][0]


def test_replace_database_configs() -> None:
    service = FakeConfigService()
    client = _create_client(service)

    resp = client.put(
        "/api/v1/config/databases",
        json={
            "databases": [
                {
                    "name": "pms",
                    "type": "postgresql",
                    "host": "localhost",
                    "port": 5432,
                    "user": "app",
                    "password": "secret",
                    "database": "pms",
                    "schema": "public",
                }
            ]
        },
    )

    assert resp.status_code == 200
    assert resp.json()["updated"] == ["pms"]


def test_database_connection_test() -> None:
    service = FakeConfigService()
    client = _create_client(service)

    resp = client.post(
        "/api/v1/config/databases/test",
        json={
            "name": "rvs",
            "type": "postgresql",
            "host": "localhost",
            "port": 5432,
            "user": "app",
            "password": "secret",
            "database": "rvs",
            "schema": "public",
        },
    )

    assert resp.status_code == 200
    assert resp.json()["success"] is True


def test_database_federation_status_distinguishes_single_database() -> None:
    client = _create_client(FakeConfigService())

    resp = client.post(
        "/api/v1/config/databases/federation-status",
        json={"db_names": ["emr"]},
    )

    assert resp.status_code == 200
    assert resp.json()["mode"] == "single"
    assert resp.json()["status"] == "not_required"


def test_database_federation_status_returns_multi_database_routes() -> None:
    client = _create_client(FakeConfigService())

    resp = client.post(
        "/api/v1/config/databases/federation-status",
        json={"db_names": ["emr", "pms", "rvs"]},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "dblink"
    assert body["status"] == "ready"
    assert sum(len(database["routes"]) for database in body["databases"]) == 6
