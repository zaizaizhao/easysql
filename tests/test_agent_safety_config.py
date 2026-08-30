from easysql.configuration.models import LLMConfig, Settings


def test_agent_timeout_has_safe_default_and_flat_env_bridge() -> None:
    assert LLMConfig().agent_timeout_seconds == 240
    assert LLMConfig().query_timeout_seconds == 300
    assert Settings(agent_timeout_seconds=90).llm.agent_timeout_seconds == 90
    assert Settings(query_timeout_seconds=120).llm.query_timeout_seconds == 120
