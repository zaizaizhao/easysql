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
