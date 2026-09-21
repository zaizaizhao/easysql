"""ADK model construction using the application's existing provider settings."""

from __future__ import annotations

from google.adk.models.lite_llm import LiteLlm

from easysql.configuration.models import LLMConfig


def create_model(config: LLMConfig) -> LiteLlm:
    provider = config.get_provider()
    name = config.get_model()
    if provider == "google_genai":
        prefix, key, base = "gemini/", config.google_api_key, None
    elif provider == "anthropic":
        prefix, key, base = "anthropic/", config.anthropic_api_key, None
    else:
        prefix, key, base = "openai/", config.openai_api_key, config.openai_api_base
    if not key:
        raise ValueError("Configure an LLM API key in the existing model settings")
    return LiteLlm(
        model=name if name.startswith(prefix) else prefix + name,
        api_key=key,
        api_base=base,
        temperature=config.temperature,
        timeout=config.agent_timeout_seconds,
        num_retries=0,
    )
