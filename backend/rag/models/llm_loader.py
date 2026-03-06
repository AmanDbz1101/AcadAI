from __future__ import annotations

import os
import logging
from typing import Any
from langchain_core.language_models import BaseChatModel
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)

_SUPPORTED_PROVIDERS = {"groq", "openai"}


def configure_tracing() -> None:
    """
    Configure LangSmith tracing from environment variables.
    
    Reads configuration from:
        - LANGCHAIN_TRACING_V2: Enable/disable tracing (true/false)
        - LANGCHAIN_API_KEY: LangSmith API key
        - LANGCHAIN_PROJECT: Project name (default: ResearchPaperAssistant)
        - LANGCHAIN_ENDPOINT: API endpoint (default: https://api.smith.langchain.com)
    
    This should be called before building the LangGraph agent.
    """
    tracing_enabled = os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true"
    
    if not tracing_enabled:
        logger.info("LangSmith tracing disabled (set LANGCHAIN_TRACING_V2=true to enable)")
        return
    
    # Set tracing environment variables
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_ENDPOINT"] = os.getenv(
        "LANGCHAIN_ENDPOINT",
        "https://api.smith.langchain.com"
    )
    os.environ["LANGCHAIN_PROJECT"] = os.getenv(
        "LANGCHAIN_PROJECT",
        "ResearchPaperAssistant"
    )
    
    api_key = os.getenv("LANGCHAIN_API_KEY")
    if api_key:
        os.environ["LANGCHAIN_API_KEY"] = api_key
        logger.info(f"✅ LangSmith tracing enabled for project: {os.environ['LANGCHAIN_PROJECT']}")
    else:
        logger.warning("⚠️  LANGCHAIN_TRACING_V2=true but LANGCHAIN_API_KEY not set")


def load_llm(
    provider: str = "groq",
    model: str = "llama-3.1-8b-instant",
    temperature: float = 0.0,
    **kwargs: Any,
) -> BaseChatModel:
    """
    Load and return a chat LLM instance.

    Args:
        provider: LLM provider name ('groq' or 'openai').
        model: Model identifier.
        temperature: Sampling temperature (0 = deterministic).
        **kwargs: Extra keyword arguments forwarded to the provider class.

    Returns:
        A LangChain BaseChatModel instance.
    """
    provider = provider.lower()

    if provider not in _SUPPORTED_PROVIDERS:
        raise ValueError(
            f"Unsupported provider '{provider}'. "
            f"Supported providers: {_SUPPORTED_PROVIDERS}"
        )

    if provider == "groq":
        return ChatGroq(model=model, temperature=temperature, **kwargs)

    if provider == "openai":
        return ChatOpenAI(model=model, temperature=temperature, **kwargs)

    raise NotImplementedError(f"Provider '{provider}' is listed but not implemented.")
