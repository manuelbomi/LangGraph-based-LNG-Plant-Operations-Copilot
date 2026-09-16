"""Provider-agnostic LLM (+ embeddings) factory.

Set `LLM_PROVIDER=openai` (default) or `LLM_PROVIDER=anthropic` in the
environment to pick a chat model backend. Every graph node that needs a
structured or plain-text completion calls `get_chat_model()`; both OpenAI's
and Anthropic's current chat models support structured/tool-call output, so
no provider-specific branching is needed beyond model construction.

`get_embeddings()` backs the maintenance-manual / past-incident semantic
search (see `app/tools/knowledge_kb.py`) -- it only ever embeds the
fictitious synthetic documents under `sample-data/` and fictitious sensor
tag/anomaly descriptions, never real plant data.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from app.config import get_settings


def get_chat_model(temperature: float | None = None) -> Any:
    """Return a LangChain chat model for the configured provider.

    Kept provider-agnostic on purpose: this repo is tested against OpenAI
    (an `OPENAI_API_KEY` is required for the live path), but swapping to
    Anthropic only requires `LLM_PROVIDER=anthropic` + `ANTHROPIC_API_KEY`.
    """
    settings = get_settings()
    temp = settings.llm_temperature if temperature is None else temperature

    if settings.llm_provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=settings.anthropic_model,
            temperature=temp,
            api_key=settings.anthropic_api_key,
        )

    # default: openai
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=settings.llm_model,
        temperature=temp,
        api_key=settings.openai_api_key,
    )


@lru_cache
def get_embeddings() -> Any:
    """Return the configured embeddings client (see module docstring)."""
    settings = get_settings()
    from langchain_openai import OpenAIEmbeddings

    return OpenAIEmbeddings(
        model=settings.embedding_model,
        api_key=settings.openai_api_key,
    )
