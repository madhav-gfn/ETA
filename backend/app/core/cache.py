"""
Shared Redis cache for expensive, hourly-fresh serving computations (the
forecast rollout, the advisory LLM copy). Redis is already provisioned
(docker-compose, requirements.txt, ``settings.redis_url``) but nothing used it
before this — every prior cache was a per-process dict/lru_cache, invisible
across workers and gone on restart.

Fail-open by design: any Redis error (down, unreachable, wrong version) is
logged once and treated as a cache miss / no-op write. Callers always fall
back to recomputing, so Redis is a pure speed optimization, never a
dependency an endpoint can 500 on. Disabled outright in ``ENVIRONMENT=test``
so the test suite never needs a Redis instance.
"""

import logging

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_client = None
_client_init_failed = False
_warned = False


def _enabled() -> bool:
    settings = get_settings()
    return settings.cache_enabled and settings.environment != "test"


def _get_client():
    """Lazy singleton. Returns None (and stays None) once construction has
    failed, so we don't retry a broken connection string every call."""
    global _client, _client_init_failed
    if _client is not None or _client_init_failed:
        return _client
    try:
        import redis  # local import: keeps redis optional for callers that never cache

        settings = get_settings()
        _client = redis.Redis.from_url(settings.redis_url, decode_responses=False)
    except Exception:
        logger.exception("Redis client construction failed — caching disabled")
        _client_init_failed = True
        _client = None
    return _client


def _warn_once(action: str) -> None:
    global _warned
    if not _warned:
        logger.warning("Redis %s failed — falling back to recompute (further failures logged at debug)", action)
        _warned = True
    else:
        logger.debug("Redis %s failed", action)


def cache_get_bytes(key: str) -> bytes | None:
    if not _enabled():
        return None
    client = _get_client()
    if client is None:
        return None
    try:
        return client.get(key)
    except Exception:
        _warn_once("GET")
        return None


def cache_set_bytes(key: str, value: bytes, ttl_seconds: int | None = None) -> None:
    if not _enabled():
        return
    client = _get_client()
    if client is None:
        return
    settings = get_settings()
    try:
        client.set(key, value, ex=ttl_seconds or settings.cache_ttl_seconds)
    except Exception:
        _warn_once("SET")


def cache_get_json(key: str) -> dict | None:
    raw = cache_get_bytes(key)
    if raw is None:
        return None
    import json

    try:
        return json.loads(raw)
    except Exception:
        logger.warning("Corrupt JSON cache entry at %s — ignoring", key)
        return None


def cache_set_json(key: str, value: dict, ttl_seconds: int | None = None) -> None:
    import json

    cache_set_bytes(key, json.dumps(value).encode("utf-8"), ttl_seconds)
