import time
import threading
import app.database.cache_utils as _cache_mod
from app.database.cache_utils import TTLCache, cache_response, _make_key


# ── TTLCache unit tests ──────────────────────────────────


class TestTTLCache:
    def test_set_and_get(self):
        """Cache stores and retrieves values."""
        cache = TTLCache(maxsize=10, ttl=60)
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_get_missing_key_returns_none(self):
        """Requesting a key that was never set returns None."""
        cache = TTLCache(maxsize=10, ttl=60)
        assert cache.get("nonexistent") is None

    def test_ttl_expiry(self):
        """Entries expire after TTL seconds."""
        cache = TTLCache(maxsize=10, ttl=1)
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

        time.sleep(1.1)
        assert cache.get("key1") is None

    def test_expired_entry_is_deleted(self):
        """Expired entries are removed from internal storage on access."""
        cache = TTLCache(maxsize=10, ttl=1)
        cache.set("key1", "value1")

        time.sleep(1.1)
        cache.get("key1")
        assert "key1" not in cache._cache

    def test_lru_eviction(self):
        """Oldest entry is evicted when cache exceeds maxsize."""
        cache = TTLCache(maxsize=3, ttl=60)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        cache.set("d", 4)  # should evict "a"

        assert cache.get("a") is None
        assert cache.get("b") == 2
        assert cache.get("d") == 4

    def test_access_refreshes_lru_order(self):
        """Accessing an entry moves it to the end, protecting from eviction."""
        cache = TTLCache(maxsize=3, ttl=60)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)

        cache.get("a")  # refresh "a" — now "b" is oldest

        cache.set("d", 4)  # should evict "b", not "a"
        assert cache.get("a") == 1
        assert cache.get("b") is None

    def test_overwrite_existing_key(self):
        """Setting an existing key updates the value."""
        cache = TTLCache(maxsize=10, ttl=60)
        cache.set("key1", "old")
        cache.set("key1", "new")
        assert cache.get("key1") == "new"

    def test_thread_safety(self):
        """Concurrent reads and writes don't corrupt the cache."""
        cache = TTLCache(maxsize=1000, ttl=60)
        errors = []

        def writer(start):
            try:
                for i in range(100):
                    cache.set(f"key-{start + i}", i)
            except Exception as e:
                errors.append(e)

        def reader(start):
            try:
                for i in range(100):
                    cache.get(f"key-{start + i}")
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=writer, args=(0,)),
            threading.Thread(target=writer, args=(100,)),
            threading.Thread(target=reader, args=(0,)),
            threading.Thread(target=reader, args=(50,)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Thread safety errors: {errors}"


# ── _make_key unit tests ──────────────────────────────────


class TestMakeKey:
    def test_same_args_produce_same_key(self):
        """Identical arguments produce the same cache key."""
        k1 = _make_key("search", ("hello", 5), {})
        k2 = _make_key("search", ("hello", 5), {})
        assert k1 == k2

    def test_different_args_produce_different_keys(self):
        """Different arguments produce different cache keys."""
        k1 = _make_key("search", ("hello", 5), {})
        k2 = _make_key("search", ("world", 5), {})
        assert k1 != k2

    def test_different_func_names_produce_different_keys(self):
        """Same args but different function names produce different keys."""
        k1 = _make_key("search", ("hello",), {})
        k2 = _make_key("query", ("hello",), {})
        assert k1 != k2

    def test_kwargs_order_does_not_matter(self):
        """Keyword arguments are sorted, so order doesn't affect the key."""
        k1 = _make_key("fn", (), {"a": 1, "b": 2})
        k2 = _make_key("fn", (), {"b": 2, "a": 1})
        assert k1 == k2

    def test_object_args_use_repr(self):
        """Object arguments are keyed by repr, making keys deterministic across restarts."""

        class Dummy:
            def __repr__(self):
                return "Dummy()"

        obj1 = Dummy()
        obj2 = Dummy()
        k1 = _make_key("fn", (obj1,), {})
        k2 = _make_key("fn", (obj2,), {})
        assert k1 == k2  # same repr = same key (deterministic)


# ── cache_response decorator tests ───────────────────────


class TestCacheResponseDecorator:
    def setup_method(self):
        """Reset the app-level cache so decorator tests use their own local caches."""
        _cache_mod._app_cache = None

    def test_caches_return_value(self):
        """Decorated function is only called once for the same arguments."""
        call_count = 0

        @cache_response(ttl=60)
        def add(a, b):
            nonlocal call_count
            call_count += 1
            return a + b

        assert add(1, 2) == 3
        assert add(1, 2) == 3  # cached
        assert call_count == 1

    def test_different_args_not_cached(self):
        """Different arguments result in separate cache entries."""
        call_count = 0

        @cache_response(ttl=60)
        def add(a, b):
            nonlocal call_count
            call_count += 1
            return a + b

        assert add(1, 2) == 3
        assert add(3, 4) == 7
        assert call_count == 2

    def test_ttl_expiry_recomputes(self):
        """After TTL expires, the function is called again."""
        call_count = 0

        @cache_response(ttl=1)
        def expensive():
            nonlocal call_count
            call_count += 1
            return "result"

        expensive()
        assert call_count == 1

        time.sleep(1.1)
        expensive()
        assert call_count == 2

    def test_works_with_kwargs(self):
        """Decorator works correctly with keyword arguments."""
        call_count = 0

        @cache_response(ttl=60)
        def greet(name, greeting="hello"):
            nonlocal call_count
            call_count += 1
            return f"{greeting} {name}"

        assert greet("alice", greeting="hi") == "hi alice"
        assert greet("alice", greeting="hi") == "hi alice"  # cached
        # different kwargs
        assert greet("alice", greeting="hey") == "hey alice"
        assert call_count == 2

    def test_works_on_instance_method(self):
        """Decorator works on class methods (self is part of the key)."""

        class Service:
            @cache_response(ttl=60)
            def compute(self, x):
                return x * 2

        svc = Service()
        assert svc.compute(5) == 10
        assert svc.compute(5) == 10  # cached

    def test_exposes_cache_attribute(self):
        """Decorated function exposes the underlying TTLCache via .cache."""

        @cache_response(ttl=60)
        def fn():
            return 1

        assert hasattr(fn, "cache")
        assert isinstance(fn.cache, TTLCache)

    def test_preserves_function_name(self):
        """functools.wraps preserves the original function metadata."""

        @cache_response(ttl=60)
        def my_function():
            """My docstring."""
            pass

        assert my_function.__name__ == "my_function"
        assert my_function.__doc__ == "My docstring."
