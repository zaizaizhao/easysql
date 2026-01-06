"""
LLM Model Factory.

Provides a unified interface to initialize ChatModels from different providers
(OpenAI, Google Gemini, Anthropic) based on configuration.
"""
import os
from typing import Literal

from langchain_core.language_models import BaseChatModel
from easysql.config import LLMConfig
from easysql.utils.logger import get_logger

logger = get_logger(__name__)

ModelType = Literal["planning", "fast"]

def get_llm(config: LLMConfig, model_type: ModelType = "planning") -> BaseChatModel:
    """
    Initialize and return a LangChain ChatModel based on configuration.
    
    Args:
        config: LLM configuration object.
        model_type: "planning" (strong model) or "fast" (weak/fast model).
        
    Returns:
        Configured BaseChatModel instance.
        
    Raises:
        ValueError: If provider is unsupported or API keys are missing.
        ImportError: If required packages are missing.
    """
    provider = config.llm_provider.lower()
    
    # Determined model name based on type
    model_name = config.model_planning if model_type == "planning" else config.model_fast
    
    logger.info(f"Initializing LLM: provider={provider}, model={model_name}, type={model_type}")
    
    if provider == "openai":
        return _init_openai(config, model_name)
    elif provider == "google_genai":
        return _init_google(config, model_name)
    elif provider == "anthropic":
        return _init_anthropic(config, model_name)
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")


def _init_openai(config: LLMConfig, model_name: str) -> BaseChatModel:
    """Initialize OpenAI ChatModel (also compatible with DeepSeek, etc.)."""
    try:
        from langchain_openai import ChatOpenAI
    except ImportError:
        raise ImportError("langchain-openai is required. Install it with: pip install langchain-openai")
    
    api_key = config.openai_api_key or os.getenv("OPENAI_API_KEY")
    api_base = config.openai_api_base or os.getenv("OPENAI_API_BASE")
    
    if not api_key:
        # Some compatible APIs might not strictly require a key if locally hosted, 
        # but usually it's needed. We'll warn if missing.
        logger.warning("OPENAI_API_KEY not found in config or env. Some requests may fail.")
        
    return ChatOpenAI(
        model=model_name,
        api_key=api_key,
        base_url=api_base,
        temperature=0,  # Deterministic for SQL gen
    )


def _init_google(config: LLMConfig, model_name: str) -> BaseChatModel:
    """Initialize Google Gemini ChatModel."""
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
    except ImportError:
        raise ImportError("langchain-google-genai is required. Install it with: pip install langchain-google-genai")
        
    api_key = config.google_api_key or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY is required for Google provider.")
        
    return ChatGoogleGenerativeAI(
        model=model_name,
        google_api_key=api_key,
        temperature=0,
    )


def _init_anthropic(config: LLMConfig, model_name: str) -> BaseChatModel:
    """Initialize Anthropic ChatModel."""
    try:
        from langchain_anthropic import ChatAnthropic
    except ImportError:
        raise ImportError("langchain-anthropic is required. Install it with: pip install langchain-anthropic")
        
    api_key = config.anthropic_api_key or os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY is required for Anthropic provider.")
        
    return ChatAnthropic(
        model=model_name,
        api_key=api_key,
        temperature=0,
    )
