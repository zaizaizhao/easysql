from easysql.config import LLMConfig
from easysql.llm.models import _build_model_kwargs


def test_default_temperature_is_zero() -> None:
    config = LLMConfig(
        openai_llm_model="gpt-4o",
        openai_api_key="fake-openai-key",
        openai_api_base="https://api.openai.com/v1",
    )

    kwargs = _build_model_kwargs(config, "openai")

    assert kwargs["temperature"] == 0


def test_temperature_follows_config_value() -> None:
    config = LLMConfig(
        openai_llm_model="kimi-k2-0711-preview",
        openai_api_key="fake-openai-key",
        openai_api_base="https://api.moonshot.cn/v1",
        temperature=1.0,
    )

    kwargs = _build_model_kwargs(config, "openai")

    assert kwargs["temperature"] == 1.0


def test_moonshot_endpoint_does_not_force_temperature() -> None:
    config = LLMConfig(
        openai_llm_model="kimi-k2-0711-preview",
        openai_api_key="fake-openai-key",
        openai_api_base="https://api.moonshot.cn/v1",
        temperature=0.3,
    )

    kwargs = _build_model_kwargs(config, "openai")

    assert kwargs["temperature"] == 0.3
