import functools
import hashlib
import json
import logging
import pickle
import threading
from collections import OrderedDict
from time import monotonic
from typing import Callable

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 300  # 5 minutes
CACHE_MAX_SIZE = 256


class TTLCache:
    """Thread-safe, size-bounded cache with per-entry TTL expiry."""

    def __init__(self, maxsize: int = CACHE_MAX_SIZE, ttl: int = CACHE_TTL_SECONDS):
        self._maxsize = maxsize
        self._ttl = ttl
        self._cache: OrderedDict[str, tuple] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str):
        with self._lock:
            if key not in self._cache:
                return None
            value, expires = self._cache[key]
            if monotonic() >= expires:
                del self._cache[key]
                return None
            self._cache.move_to_end(key)
            return value

    def set(self, key: str, value):
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = (value, monotonic() + self._ttl)
            if len(self._cache) > self._maxsize:
                self._cache.popitem(last=False)


class RedisCache:
    """Redis-backed cache with the same get/set interface as TTLCache.

    All Redis operations are wrapped in try/except so a Redis failure
    never crashes the application.
    """

    def __init__(self, redis_url: str, ttl: int = CACHE_TTL_SECONDS):
        import redis as _redis

        self._ttl = ttl
        self._pool = _redis.ConnectionPool.from_url(redis_url)
        self._client = _redis.Redis(connection_pool=self._pool)

    def get(self, key: str):
        try:
            raw = self._client.get(key)
            if raw is None:
                return None
            # Try JSON first, fall back to pickle
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, UnicodeDecodeError):
                return pickle.loads(raw)
        except Exception:
            logger.warning("RedisCache.get failed for key=%s, returning None", key)
            return None

    def set(self, key: str, value):
        try:
            # Try JSON serialization first, fall back to pickle
            try:
                serialized = json.dumps(value)
            except (TypeError, ValueError):
                serialized = pickle.dumps(value)
            self._client.setex(key, self._ttl, serialized)
        except Exception:
            logger.warning("RedisCache.set failed for key=%s, value not cached", key)

    def ping(self) -> bool:
        """Return True if Redis is reachable."""
        try:
            return self._client.ping()
        except Exception:
            return False


def get_cache(
    redis_url: str | None = None,
    ttl: int = CACHE_TTL_SECONDS,
    maxsize: int = CACHE_MAX_SIZE,
) -> TTLCache | RedisCache:
    """Factory: return a RedisCache if Redis is reachable, else a TTLCache."""
    if redis_url:
        try:
            cache = RedisCache(redis_url=redis_url, ttl=ttl)
            if cache.ping():
                logger.info("Using RedisCache at %s", redis_url)
                return cache
            logger.warning("Redis not reachable at %s, falling back to TTLCache", redis_url)
        except Exception:
            logger.warning("Failed to create RedisCache, falling back to TTLCache")
    return TTLCache(maxsize=maxsize, ttl=ttl)


def _make_key(func_name: str, args: tuple, kwargs: dict) -> str:
    """Build a stable, hashable cache key from function name + arguments."""
    parts = [func_name]
    for arg in args:
        parts.append(f"{type(arg).__name__}:{repr(arg)}")  # noqa: E231
    for k, v in sorted(kwargs.items()):
        parts.append(f"{k}={repr(v)}")
    raw = "|".join(parts)
    return hashlib.md5(raw.encode()).hexdigest()


# Module-level app cache — set at startup via set_app_cache().
# If set, all @cache_response decorators use it instead of per-decorator TTLCache.
_app_cache = None


def set_app_cache(cache):
    """Set the application-wide cache instance (called once at startup)."""
    global _app_cache
    _app_cache = cache


def cache_response(ttl: int = CACHE_TTL_SECONDS, cache=None):
    """Decorator that caches function results with TTL expiry and LRU eviction.

    Cache resolution order:
    1. Explicit `cache` parameter (if provided)
    2. App-level cache set via set_app_cache() (if set)
    3. A local TTLCache (fallback, preserves original behaviour)
    """
    _local_cache = cache if cache is not None else TTLCache(maxsize=CACHE_MAX_SIZE, ttl=ttl)

    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            active_cache = _app_cache if _app_cache is not None else _local_cache
            key = _make_key(func.__name__, args, kwargs)
            cached = active_cache.get(key)
            if cached is not None:
                return cached
            result = func(*args, **kwargs)
            active_cache.set(key, result)
            return result

        wrapper.cache = _local_cache
        return wrapper

    return decorator
