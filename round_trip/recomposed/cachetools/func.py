"""
functools.lru_cache-compatible decorators backed by cachetools caches.
"""

import math
import time

try:
    from threading import RLock
except ImportError:
    from dummy_threading import RLock

from . import FIFOCache, LFUCache, LRUCache, MRUCache, RRCache, TTLCache
from . import cached
from . import keys


__all__ = [
    "fifo_cache",
    "lfu_cache",
    "lru_cache",
    "mru_cache",
    "rr_cache",
    "ttl_cache",
]


class _UnboundTTLCache(TTLCache):
    """TTLCache with maxsize=inf."""

    def __init__(self, ttl, timer):
        TTLCache.__init__(self, math.inf, ttl, timer)

    @property
    def maxsize(self):
        return None

    def popitem(self):
        raise KeyError("cache is full")


def _cache(cache_cls, maxsize, typed, **kwargs):
    """Build a cache instance based on maxsize."""
    if maxsize is None or (isinstance(maxsize, float) and math.isinf(maxsize)):
        # Use a plain dict for unbounded caches (except TTLCache)
        cache_obj = {}
    elif maxsize == 0:
        cache_obj = cache_cls(0, **kwargs)
    else:
        cache_obj = cache_cls(maxsize, **kwargs)

    key = keys.typedkey if typed else keys.hashkey
    return cache_obj, key


def _make_wrapper(cache_cls, maxsize, typed, func, **kwargs):
    """Create a cached wrapper with cache_parameters."""
    if maxsize is None or (isinstance(maxsize, float) and math.isinf(maxsize)):
        cache_obj = {}
    elif maxsize == 0:
        cache_obj = cache_cls(0, **kwargs)
    else:
        cache_obj = cache_cls(maxsize, **kwargs)

    key = keys.typedkey if typed else keys.hashkey
    lock = RLock()
    wrapper = cached(cache_obj, key=key, lock=lock, info=True)(func)
    wrapper.cache_parameters = lambda: {"maxsize": maxsize, "typed": typed}
    return wrapper


def fifo_cache(maxsize=128, typed=False):
    """Decorator backed by FIFOCache."""
    if callable(maxsize):
        # Bare decorator usage: @fifo_cache
        func = maxsize
        return _make_wrapper(FIFOCache, 128, False, func)

    def decorator(func):
        return _make_wrapper(FIFOCache, maxsize, typed, func)

    return decorator


def lfu_cache(maxsize=128, typed=False):
    """Decorator backed by LFUCache."""
    if callable(maxsize):
        func = maxsize
        return _make_wrapper(LFUCache, 128, False, func)

    def decorator(func):
        return _make_wrapper(LFUCache, maxsize, typed, func)

    return decorator


def lru_cache(maxsize=128, typed=False):
    """Decorator backed by LRUCache."""
    if callable(maxsize):
        func = maxsize
        return _make_wrapper(LRUCache, 128, False, func)

    def decorator(func):
        return _make_wrapper(LRUCache, maxsize, typed, func)

    return decorator


def mru_cache(maxsize=128, typed=False):
    """Deprecated. Decorator backed by MRUCache."""
    if callable(maxsize):
        func = maxsize
        return _make_wrapper(MRUCache, 128, False, func)

    def decorator(func):
        return _make_wrapper(MRUCache, maxsize, typed, func)

    return decorator


def rr_cache(maxsize=128, typed=False):
    """Decorator backed by RRCache."""
    if callable(maxsize):
        func = maxsize
        return _make_wrapper(RRCache, 128, False, func)

    def decorator(func):
        return _make_wrapper(RRCache, maxsize, typed, func)

    return decorator


def ttl_cache(maxsize=128, ttl=600, timer=None, typed=False):
    """Decorator backed by TTLCache."""
    if callable(maxsize):
        # Bare decorator usage
        func = maxsize
        actual_timer = time.monotonic
        return _make_ttl_wrapper(128, 600, actual_timer, False, func)

    def decorator(func):
        actual_timer = timer if timer is not None else time.monotonic
        return _make_ttl_wrapper(maxsize, ttl, actual_timer, typed, func)

    return decorator


def _make_ttl_wrapper(maxsize, ttl, timer, typed, func):
    """Create a TTL cached wrapper."""
    if maxsize is None or (isinstance(maxsize, float) and math.isinf(maxsize)):
        cache_obj = _UnboundTTLCache(ttl=ttl, timer=timer)
    elif maxsize == 0:
        cache_obj = TTLCache(0, ttl=ttl, timer=timer)
    else:
        cache_obj = TTLCache(maxsize, ttl=ttl, timer=timer)

    key = keys.typedkey if typed else keys.hashkey
    lock = RLock()
    wrapper = cached(cache_obj, key=key, lock=lock, info=True)(func)
    wrapper.cache_parameters = lambda: {"maxsize": maxsize, "typed": typed}
    return wrapper
