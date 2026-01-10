"""
LLM Model Factory.

Provides a unified interface to initialize ChatModels from different providers
using LangChain's init_chat_model for maximum flexibility.
"""

import os
from typing import Any, Literal, cast

from langchain_core.language_models import BaseChatModel
from easysql.config import LLMConfig
from easysql.utils.logger import get_logger

logger = get_logger(__name__)

# Purpose: "generation" for SQL generation/repair, "planning" for analyze/clarify
ModelPurpose = Literal["generation", "planning"]

# Provider name mapping for init_chat_model
PROVIDER_MAPPING: dict[str, str] = {
    "openai": "openai",
    "google_genai": "google_genai",
    "google": "google_genai",
    "anthropic": "anthropic",
    "ollama": "ollama",
}


def get_llm(config: LLMConfig, purpose: ModelPurpose = "generation") -> BaseChatModel:
    """
    Initialize and return a LangChain ChatModel based on configuration.

    Args:
        config: LLM configuration object.
        purpose: "generation" or "planning".

    Returns:
        Configured BaseChatModel instance.

    Raises:
        ValueError: If provider is unsupported.
    """
    # Determine provider and model based on priority
    provider = config.get_provider()

    if purpose == "planning" and config.model_planning:
        model_name = config.model_planning
    else:
        model_name = config.get_model()

    logger.info(f"Initializing LLM: provider={provider}, model={model_name}, purpose={purpose}")

    model_kwargs = _build_model_kwargs(config, provider)

    return _init_chat_model(provider, model_name, model_kwargs)


def _build_model_kwargs(config: LLMConfig, provider: str) -> dict[str, Any]:
    """Build model initialization kwargs based on provider."""
    kwargs: dict[str, Any] = {
        "temperature": 0,  # Deterministic for SQL generation
    }

    if provider == "openai":
        api_key = config.openai_api_key or os.getenv("OPENAI_API_KEY")
        api_base = config.openai_api_base or os.getenv("OPENAI_API_BASE")

        if api_key:
            kwargs["api_key"] = api_key
        if api_base and api_base != "https://api.openai.com/v1":
            kwargs["base_url"] = api_base

    elif provider == "google_genai":
        api_key = config.google_api_key or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY is required for Google provider.")
        kwargs["google_api_key"] = api_key

    elif provider == "anthropic":
        api_key = config.anthropic_api_key or os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is required for Anthropic provider.")
        kwargs["api_key"] = api_key

    return kwargs


def _init_chat_model(provider: str, model_name: str, model_kwargs: dict[str, Any]) -> BaseChatModel:
    """Initialize chat model using LangChain's init_chat_model."""
    lc_provider = PROVIDER_MAPPING.get(provider, provider)

    try:
        from langchain.chat_models import init_chat_model

        return cast(BaseChatModel, init_chat_model(model=model_name, model_provider=lc_provider, **model_kwargs))
    except ImportError:
        logger.debug("init_chat_model not available, using fallback")
        return _init_chat_model_direct(provider, model_name, model_kwargs)
    except Exception as e:
        logger.warning(f"init_chat_model failed: {e}, using fallback")
        return _init_chat_model_direct(provider, model_name, model_kwargs)


def _init_chat_model_direct(
    provider: str, model_name: str, model_kwargs: dict[str, Any]
) -> BaseChatModel:
    """Direct model instantiation fallback."""
    if provider == "openai":
        try:
            from langchain_openai import ChatOpenAI
        except ImportError:
            raise ImportError("pip install langchain-openai")
        return cast(BaseChatModel, ChatOpenAI(model=model_name, **model_kwargs))

    elif provider == "google_genai":
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError:
            raise ImportError("pip install langchain-google-genai")
        return cast(BaseChatModel, ChatGoogleGenerativeAI(model=model_name, **model_kwargs))

    elif provider == "anthropic":
        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError:
            raise ImportError("pip install langchain-anthropic")
        return cast(BaseChatModel, ChatAnthropic(model_name=model_name, **model_kwargs))

    elif provider == "ollama":
        try:
            from langchain_ollama import ChatOllama
        except ImportError:
            raise ImportError("pip install langchain-ollama")
        return cast(BaseChatModel, ChatOllama(model=model_name, **model_kwargs))

    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")
