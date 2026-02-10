from easysql.config import LangfuseConfig


def test_langfuse_base_url_takes_precedence(monkeypatch) -> None:
    monkeypatch.delenv("LANGFUSE_BASE_URL", raising=False)
    monkeypatch.delenv("LANGFUSE_HOST", raising=False)
    monkeypatch.setenv("LANGFUSE_BASE_URL", "https://base.example")
    monkeypatch.setenv("LANGFUSE_HOST", "https://host.example")

    config = LangfuseConfig(_env_file=None)
    assert config.host == "https://base.example"


def test_langfuse_host_legacy_fallback(monkeypatch) -> None:
    monkeypatch.delenv("LANGFUSE_BASE_URL", raising=False)
    monkeypatch.delenv("LANGFUSE_HOST", raising=False)
    monkeypatch.setenv("LANGFUSE_HOST", "https://host.example")

    config = LangfuseConfig(_env_file=None)
    assert config.host == "https://host.example"
