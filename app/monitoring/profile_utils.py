import inspect
import time
import functools
import logging


def profile(func):
    """Profile execution time for both sync and async functions."""
    logger = logging.getLogger("monster_resort")

    if inspect.iscoroutinefunction(func):

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            start = time.perf_counter()
            result = await func(*args, **kwargs)
            elapsed = time.perf_counter() - start
            logger.info(f"[PROFILE] {func.__name__} took {elapsed:.4f}s")  # noqa: E231
            return result

        return async_wrapper
    else:

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            start = time.perf_counter()
            result = func(*args, **kwargs)
            elapsed = time.perf_counter() - start
            logger.info(f"[PROFILE] {func.__name__} took {elapsed:.4f}s")  # noqa: E231
            return result

        return sync_wrapper
