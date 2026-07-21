"""
Thin LLM wrapper (Step 6) — provider pluggable via LLM_PROVIDER (groq default,
anthropic alternative). Every call degrades gracefully: on missing key or any
API failure the caller gets None and falls back to its deterministic template,
so the pipeline can never be blocked by an LLM outage. Clients are cached at
module level and carry a hard timeout so an agent run can't hang on a slow
provider.
"""

import logging
from functools import lru_cache

from app.core.config import get_settings

logger = logging.getLogger(__name__)

GROQ_MODEL = "llama-3.3-70b-versatile"
ANTHROPIC_MODEL = "claude-sonnet-5"
TIMEOUT_S = 15.0
MAX_RETRIES = 1


@lru_cache(maxsize=1)
def _anthropic_client():
    import anthropic

    return anthropic.Anthropic(
        api_key=get_settings().anthropic_api_key, timeout=TIMEOUT_S, max_retries=MAX_RETRIES
    )


@lru_cache(maxsize=1)
def _groq_client():
    from groq import Groq

    return Groq(api_key=get_settings().groq_api_key, timeout=TIMEOUT_S, max_retries=MAX_RETRIES)


def complete(system: str, user: str, max_tokens: int = 600) -> str | None:
    settings = get_settings()
    provider = getattr(settings, "llm_provider", "groq") or "groq"
    try:
        if provider == "anthropic" and settings.anthropic_api_key:
            resp = _anthropic_client().messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            return resp.content[0].text
        if settings.groq_api_key:
            resp = _groq_client().chat.completions.create(
                model=GROQ_MODEL,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
            return resp.choices[0].message.content
    except Exception:
        logger.exception("LLM call failed — falling back to deterministic output")
    return None
