from __future__ import annotations

from easysql_api.services import cache_invalidator as module
from easysql_api.services.cache_invalidator import CacheInvalidator


class DummySettingsGetter:
    def __init__(self) -> None:
        self.cleared = 0

    def cache_clear(self) -> None:
        self.cleared += 1


def test_invalidate_dispatches_by_tags(monkeypatch) -> None:
    settings_getter = DummySettingsGetter()
    called: dict[str, int] = {}

    def _mark(name: str):
        called[name] = called.get(name, 0) + 1

    monkeypatch.setattr(module, "get_settings", settings_getter)
    monkeypatch.setattr(module, "reset_query_service_graph", lambda: _mark("query_graph"))
    monkeypatch.setattr(module, "reset_query_service_callbacks", lambda: _mark("query_callbacks"))
    monkeypatch.setattr(module, "reset_chart_service_callbacks", lambda: _mark("chart_callbacks"))
    monkeypatch.setattr(module, "reset_retrieval_service_cache", lambda: _mark("retrieval_cache"))
    monkeypatch.setattr(module, "reset_retrieve_hint_readers_cache", lambda: _mark("hint_cache"))
    monkeypatch.setattr(module, "reset_few_shot_reader_cache", lambda: _mark("few_shot_cache"))
    monkeypatch.setattr(module, "reset_code_retrieval_service_cache", lambda: _mark("code_cache"))

    invalidator = CacheInvalidator()
    invalidator.invalidate(
        {
            "graph",
            "callbacks",
            "retrieval_cache",
            "few_shot_cache",
            "code_context_cache",
        }
    )

    assert settings_getter.cleared == 1
    assert called["query_graph"] == 1
    assert called["query_callbacks"] == 1
    assert called["chart_callbacks"] == 1
    assert called["retrieval_cache"] == 1
    assert called["hint_cache"] == 1
    assert called["few_shot_cache"] == 1
    assert called["code_cache"] == 1


def test_warmup_dispatches_by_tags(monkeypatch) -> None:
    called: dict[str, int] = {}

    def _mark(name: str) -> None:
        called[name] = called.get(name, 0) + 1

    monkeypatch.setattr(module, "warm_query_service_graph", lambda: _mark("query_graph"))
    monkeypatch.setattr(module, "warm_query_service_callbacks", lambda: _mark("query_callbacks"))
    monkeypatch.setattr(module, "warm_chart_service_callbacks", lambda: _mark("chart_callbacks"))
    monkeypatch.setattr(module, "warm_retrieval_service_cache", lambda: _mark("retrieval_cache"))
    monkeypatch.setattr(module, "warm_retrieve_hint_readers_cache", lambda: _mark("hint_cache"))
    monkeypatch.setattr(module, "warm_few_shot_reader_cache", lambda: _mark("few_shot_cache"))
    monkeypatch.setattr(module, "warm_code_retrieval_service_cache", lambda: _mark("code_cache"))

    invalidator = CacheInvalidator()
    invalidator.warmup(
        {"graph", "callbacks", "retrieval_cache", "few_shot_cache", "code_context_cache"}
    )

    assert called["query_graph"] == 1
    assert called["query_callbacks"] == 1
    assert called["chart_callbacks"] == 1
    assert called["retrieval_cache"] == 1
    assert called["hint_cache"] == 1
    assert called["few_shot_cache"] == 1
    assert called["code_cache"] == 1
