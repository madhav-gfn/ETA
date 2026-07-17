"""
Thin LLM wrapper (Step 6) — provider pluggable via LLM_PROVIDER (groq default,
anthropic alternative). Every call degrades gracefully: on missing key or any
API failure the caller gets None and falls back to its deterministic template,
so the demo can never be blocked by an LLM outage.
"""

import logging

from app.core.config import get_settings

logger = logging.getLogger(__name__)

GROQ_MODEL = "llama-3.3-70b-versatile"
ANTHROPIC_MODEL = "claude-sonnet-5"


def complete(system: str, user: str, max_tokens: int = 600) -> str | None:
    settings = get_settings()
    provider = getattr(settings, "llm_provider", "groq") or "groq"
    try:
        if provider == "anthropic" and settings.anthropic_api_key:
            import anthropic

            client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
            resp = client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            return resp.content[0].text
        if settings.groq_api_key:
            from groq import Groq

            client = Groq(api_key=settings.groq_api_key)
            resp = client.chat.completions.create(
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
