"""LLM tool — model-independent LLM invocation via LiteLLM.

LiteLLM exposes one call signature (`litellm.acompletion`) across every
provider — OpenAI, Anthropic, Azure, Bedrock, Ollama, etc. This module never
hardcodes a provider: it forwards `settings.llm_model` (any LiteLLM model
string, e.g. "gpt-4o-mini", "anthropic/claude-3-5-sonnet", "ollama/llama3")
straight through, so swapping providers is a config change, not a code change.

Disabled by default (`APP_LLM_ENABLED=false`), so the extraction pipeline
stays fully deterministic and network-free unless a team opts in. Every
call site in the app is expected to treat `None` as "fall back to the
heuristic path" rather than treat an LLM failure as fatal.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def is_enabled() -> bool:
    return settings.llm_enabled


async def complete(prompt: str, system: Optional[str] = None, max_tokens: int = 500) -> Optional[str]:
    """Return a raw LLM completion, or None if disabled/unavailable/failed."""
    if not settings.llm_enabled:
        return None
    try:
        import litellm
    except ImportError:
        logger.warning("APP_LLM_ENABLED=true but `litellm` is not installed; skipping LLM call")
        return None

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    logger.debug("llm request model=%s prompt=%.300s", settings.llm_model, prompt)
    try:
        response = await litellm.acompletion(
            model=settings.llm_model,
            messages=messages,
            api_key=settings.llm_api_key or None,
            api_base=settings.llm_api_base or None,
            max_tokens=max_tokens,
            timeout=settings.llm_timeout_seconds,
        )
        content = response["choices"][0]["message"]["content"]
        logger.debug("llm response model=%s content=%.300s", settings.llm_model, content)
        return content.strip() if content else None
    except Exception:  # noqa: BLE001 - LLM calls are best-effort, never fatal
        logger.warning(
            "LLM completion failed (model=%s); falling back to heuristic output",
            settings.llm_model,
            exc_info=True,
        )
        return None


async def complete_json(prompt: str, system: Optional[str] = None, max_tokens: int = 800) -> Optional[Any]:
    """Ask the LLM for a JSON response and parse it. Returns None on any
    failure (disabled, network error, invalid JSON) so callers can fall
    back to heuristics unconditionally instead of special-casing errors."""
    raw = await complete(prompt, system=system, max_tokens=max_tokens)
    if raw is None:
        return None

    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text[:4].lower() == "json":
            text = text[4:]

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning("LLM returned non-JSON output; falling back to heuristic. raw=%.300s", raw)
        return None
