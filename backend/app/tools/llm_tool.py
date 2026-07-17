"""LLM tool — pluggable via LiteLLM, disabled by default.

The core extraction pipeline is fully heuristic/offline so it never
requires an LLM (or network access, or `litellm` even being installed) to
produce results. Set `APP_LLM_ENABLED=true` (and install
`requirements-optional.txt`) to let subagents call out to an LLM for
enhancement — e.g. turning a mined rule's condition/action into a more
naturally-worded sentence.
"""
from __future__ import annotations

from typing import Optional

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


async def complete(prompt: str, max_tokens: int = 200) -> Optional[str]:
    """Return an LLM completion, or None if LLM support is disabled/unavailable/failed."""
    if not settings.llm_enabled:
        return None
    try:
        import litellm
    except ImportError:
        logger.warning("APP_LLM_ENABLED=true but `litellm` is not installed; skipping LLM enhancement")
        return None

    try:
        response = await litellm.acompletion(
            model=settings.llm_model,
            messages=[{"role": "user", "content": prompt}],
            api_key=settings.llm_api_key or None,
            max_tokens=max_tokens,
        )
        return response["choices"][0]["message"]["content"].strip()
    except Exception:  # noqa: BLE001 - LLM enhancement is best-effort, never fatal
        logger.warning("LLM completion failed; falling back to heuristic output", exc_info=True)
        return None
