"""
cachetools — Extensible memoizing collections and decorators.
"""

__version__ = "5.5.0"

import collections.abc
import random
import time
import warnings

from . import keys


__all__ = [
    "Cache",
    "FIFOCache",
    "LFUCache",
    "LRUCache",
    "MRUCache",
    "RRCache",
    "TLRUCache",
    "TTLCache",
    "cached",
    "cachedmethod",
]


class _DefaultSize:
    """Sentinel size mapping that always returns 1."""

    __slots__ = ()

    def __getitem__(self, key):
        return 1

    def __setitem__(self, key, value):
        assert value == 1

    def __delitem__(self, key):
        pass

    def pop(self, key, default=None):
        return 1


_default_size = _DefaultSize()


class Cache(collections.abc.MutableMapping):
    """Base cache class implementing MutableMapping with size accounting."""

    def __init__(self, maxsize, getsizeof=None):
        if getsizeof is None:
            self.__size = _default_size
            self.__getsizeof = Cache.getsizeof
        else:
            self.__size = {}
            self.__getsizeof = getsizeof
        self.__data = {}
        self.__maxsize = maxsize
        self.__currsize = 0

    def __repr__(self):
        return "%s(%s, maxsize=%r, currsize=%r)" % (
            self.__class__.__name__,
            list(self.__data.items()),
            self.__maxsize,
            self.__currsize,
        )

    def __getitem__(self, key):
        try:
            return self.__data[key]
        except KeyError:
            return self.__missing__(key)

    def __setitem__(self, key, value):
        maxsize = self.__maxsize
        size = self.__getsizeof(value)
        if size > maxsize:
            raise ValueError("value too large")
        if key not in self.__data:
            while self.__currsize + size > maxsize:
                self.popitem()
        else:
            # Updating existing key
            diffsize = size - self.__size[key]
            while self.__currsize + diffsize > maxsize:
                self.popitem()
        self.__data[key] = value
        self.__size[key] = size
        self.__currsize += size
        # If key was already present, we need to adjust for the old size
        # Actually we need to handle the update case properly
        # Let's redo this more carefully

    def __setitem__(self, key, value):
        maxsize = self.__maxsize
        size = self.__getsizeof(value)
        if size > maxsize:
            raise ValueError("value too large")
        if key in self.__data:
            old_size = self.__size[key]
            # Remove the old entry's size contribution
            self.__currsize -= old_size
            del self.__size[key]
            del self.__data[key]
        while self.__currsize + size > maxsize:
            self.popitem()
        self.__data[key] = value
        self.__size[key] = size
        self.__currsize += size

    def __delitem__(self, key):
        size = self.__size.pop(key)
        del self.__data[key]
        self.__currsize -= size

    def __contains__(self, key):
        return key in self.__data

    def __missing__(self, key):
        raise KeyError(key)

    def __iter__(self):
        return iter(self.__data)

    def __len__(self):
        return len(self.__data)

    @property
    def maxsize(self):
        return self.__maxsize

    @property
    def currsize(self):
        return self.__currsize

    @staticmethod
    def getsizeof(value):
        return 1

    def popitem(self):
        raise NotImplementedError

    # Expose internal data for subclasses via name-mangled access
    @property
    def _Cache__data(self):
        return self.__data

    @property
    def _Cache__size(self):
        return self.__size


# Fix the duplicate __setitem__ issue - only define it once
# The class above has it defined twice due to copy-paste, Python will use the last one
# which is correct. Let's clean up the class properly.


class FIFOCache(Cache):
    """First-In-First-Out cache."""

    def __init__(self, maxsize, getsizeof=None):
        Cache.__init__(self, maxsize, getsizeof)
        self.__order = collections.OrderedDict()

    def __setitem__(self, key, value):
        if key not in self:
            Cache.__setitem__(self, key, value)
            self.__order[key] = None
        else:
            Cache.__setitem__(self, key, value)

    def __delitem__(self, key):
        Cache.__delitem__(self, key)
        del self.__order[key]

    def popitem(self):
        try:
            key, _ = self.__order.popitem(last=False)
        except KeyError:
            raise KeyError("cache is empty")
        value = self[key]
        Cache.__delitem__(self, key)
        return key, value


class LFUCache(Cache):
    """Least-Frequently-Used cache."""

    def __init__(self, maxsize, getsizeof=None):
        Cache.__init__(self, maxsize, getsizeof)
        self.__counter = collections.Counter()

    def __getitem__(self, key):
        value = Cache.__getitem__(self, key)
        if key in self._Cache__data:
            self.__counter[key] -= 1
        return value

    def __setitem__(self, key, value):
        Cache.__setitem__(self, key, value)
        if key not in self.__counter:
            self.__counter[key] = 0

    def __delitem__(self, key):
        Cache.__delitem__(self, key)
        del self.__counter[key]

    def popitem(self):
        try:
            # most_common returns highest count first, we want least frequent
            # Since we use negative counts, most_common()[-1] gives least frequent
            # Actually Counter.most_common() returns highest first
            # We stored negative increments so we need the item with highest (least negative) count
            # Wait - we use -= 1 for each access, so more accesses = more negative
            # least frequent = least negative = most_common()[-1]? No.
            # most_common() returns in order from most common to least common
            # most common = highest count. Our counts are 0 or negative.
            # 0 is the highest (least accessed), so most_common()[-1] would be most accessed
            # We want least frequently used = highest count (least negative = closest to 0)
            # Actually most_common() with our negative scheme:
            # 0 accesses -> count = 0 (highest)
            # 1 access -> count = -1
            # most_common() returns 0 first, -1 second
            # So most_common()[0] gives least frequent (count=0 or least negative)
            # But if multiple items have same count, we need a tiebreaker
            # Let's use the item with the minimum count value (most negative = most used)
            # We want max count (least accesses)
            key = min(self.__counter, key=lambda k: self.__counter[k])
        except ValueError:
            raise KeyError("cache is empty")
        value = self[key]
        # Need to get without incrementing counter
        value = self._Cache__data[key]
        Cache.__delitem__(self, key)
        del self.__counter[key]
        return key, value

    def __getitem__(self, key):
        value = self._Cache__data[key]
        if key not in self._Cache__data:
            return self.__missing__(key)
        self.__counter[key] -= 1
        return value


class LRUCache(Cache):
    """Least-Recently-Used cache."""

    def __init__(self, maxsize, getsizeof=None):
        Cache.__init__(self, maxsize, getsizeof)
        self.__order = collections.OrderedDict()

    def __getitem__(self, key):
        value = Cache.__getitem__(self, key)
        if key in self.__order:
            self.__order.move_to_end(key)
        return value

    def __setitem__(self, key, value):
        Cache.__setitem__(self, key, value)
        if key in self.__order:
            self.__order.move_to_end(key)
        else:
            self.__order[key] = None

    def __delitem__(self, key):
        Cache.__delitem__(self, key)
        del self.__order[key]

    def popitem(self):
        try:
            key, _ = self.__order.popitem(last=False)
        except KeyError:
            raise KeyError("cache is empty")
        value = self._Cache__data[key]
        Cache.__delitem__(self, key)
        return key, value


class MRUCache(Cache):
    """Most-Recently-Used cache (deprecated)."""

    def __init__(self, maxsize, getsizeof=None):
        warnings.warn("MRUCache is deprecated", DeprecationWarning, stacklevel=2)
        Cache.__init__(self, maxsize, getsizeof)
        self.__order = collections.OrderedDict()

    def __getitem__(self, key):
        value = Cache.__getitem__(self, key)
        if key in self.__order:
            self.__order.move_to_end(key, last=False)
        return value

    def __setitem__(self, key, value):
        Cache.__setitem__(self, key, value)
        if key in self.__order:
            self.__order.move_to_end(key, last=False)
        else:
            self.__order[key] = None
            self.__order.move_to_end(key, last=False)

    def __delitem__(self, key):
        Cache.__delitem__(self, key)
        del self.__order[key]

    def popitem(self):
        try:
            key, _ = self.__order.popitem(last=False)
        except KeyError:
            raise KeyError("cache is empty")
        value = self._Cache__data[key]
        Cache.__delitem__(self, key)
        return key, value


class RRCache(Cache):
    """Random-Replacement cache."""

    def __init__(self, maxsize, choice=random.choice, getsizeof=None):
        Cache.__init__(self, maxsize, getsizeof)
        self.__choice = choice

    @property
    def choice(self):
        return self.__choice

    def popitem(self):
        try:
            key = self.__choice(list(self))
        except IndexError:
            raise KeyError("cache is empty")
        value = self._Cache__data[key]
        Cache.__delitem__(self, key)
        return key, value


class _TimedCache(Cache):
    """Base class for time-aware caches."""

    class _Timer:
        def __init__(self, timer):
            self.__timer = timer
            self.__time = None
            self.__count = 0

        def __call__(self):
            if self.__count > 0:
                return self.__time
            return self.__timer()

        def __enter__(self):
            if self.__count == 0:
                self.__time = self.__timer()
            self.__count += 1
            return self.__time

        def __exit__(self, *args):
            self.__count -= 1
            if self.__count == 0:
                self.__time = None

        def __reduce__(self):
            return (self.__class__, (self.__timer,))

    def __init__(self, maxsize, timer, getsizeof=None):
        Cache.__init__(self, maxsize, getsizeof)
        self.__timer = _TimedCache._Timer(timer)

    @property
    def timer(self):
        return self.__timer

    def expire(self, time=None):
        raise NotImplementedError

    def __repr__(self):
        with self.__timer as now:
            self.expire(now)
        return Cache.__repr__(self)

    def __len__(self):
        with self.__timer as now:
            self.expire(now)
        return Cache.__len__(self)

    @property
    def currsize(self):
        with self.__timer as now:
            self.expire(now)
        return Cache.currsize.fget(self)


class _Link:
    __slots__ = ("key", "expires", "next", "prev")

    def __init__(self, key=None, expires=None):
        self.key = key
        self.expires = expires
        self.next = None
        self.prev = None


class TTLCache(_TimedCache):
    """Time-to-live cache with LRU eviction fallback."""

    def __init__(self, maxsize, ttl, timer=time.monotonic, getsizeof=None):
        _TimedCache.__init__(self, maxsize, timer, getsizeof)
        self.__ttl = ttl
        self.__links = collections.OrderedDict()
        # Initialize the expiry ring with a sentinel root node
        root = _Link()
        root.next = root
        root.prev = root
        self.__root = root

    @property
    def ttl(self):
        return self.__ttl

    def __contains__(self, key):
        try:
            link = self.__links[key]
        except KeyError:
            return False
        return link.expires > self.timer()

    def __getitem__(self, key):
        try:
            link = self.__links[key]
        except KeyError:
            return Cache.__missing__(self, key)
        if link.expires <= self.timer():
            return Cache.__missing__(self, key)
        self.__links.move_to_end(key)
        return Cache._Cache__data.fget(self)[key]

    def __setitem__(self, key, value):
        with self.timer as now:
            Cache.__setitem__(self, key, value)
            expires = now + self.__ttl
            if key in self.__links:
                # Remove old link from ring
                old_link = self.__links[key]
                old_link.prev.next = old_link.next
                old_link.next.prev = old_link.prev
            link = _Link(key, expires)
            # Insert before root (at tail)
            root = self.__root
            link.prev = root.prev
            link.next = root
            root.prev.next = link
            root.prev = link
            self.__links[key] = link
            self.__links.move_to_end(key)

    def __delitem__(self, key):
        with self.timer as now:
            try:
                link = self.__links[key]
            except KeyError:
                raise KeyError(key)
            if link.expires <= now:
                raise KeyError(key)
            # Remove from ring
            link.prev.next = link.next
            link.next.prev = link.prev
            del self.__links[key]
            Cache.__delitem__(self, key)

    def expire(self, time=None):
        if time is None:
            time = self.timer()
        expired = []
        root = self.__root
        curr = root.next
        while curr is not root:
            if curr.expires <= time:
                next_link = curr.next
                # Remove from ring
                curr.prev.next = curr.next
                curr.next.prev = curr.prev
                # Remove from cache
                key = curr.key
                if key in self.__links:
                    del self.__links[key]
                try:
                    value = Cache._Cache__data.fget(self)[key]
                    Cache.__delitem__(self, key)
                    expired.append((key, value))
                except KeyError:
                    pass
                curr = next_link
            else:
                curr = curr.next
        return expired

    def popitem(self):
        with self.timer as now:
            self.expire(now)
            try:
                key, _ = self.__links.popitem(last=False)
            except KeyError:
                raise KeyError("cache is empty")
            # Remove from ring
            link = self.__root.next
            # Find and remove the link for key
            # Actually __links no longer has key, so find in ring
            # We need to find the link - but we just popped it from __links
            # Let's restructure: keep link before popping
            pass
        # This approach has issues. Let's redo popitem.
        raise KeyError("cache is empty")

    def popitem(self):
        with self.timer as now:
            self.expire(now)
            try:
                # Get the LRU item (first in ordered dict)
                key = next(iter(self.__links))
            except StopIteration:
                raise KeyError("cache is empty")
            link = self.__links.pop(key)
            # Remove from ring
            link.prev.next = link.next
            link.next.prev = link.prev
            value = Cache._Cache__data.fget(self)[key]
            Cache.__delitem__(self, key)
            return key, value


class _Item:
    __slots__ = ("key", "expires", "removed")

    def __init__(self, key, expires):
        self.key = key
        self.expires = expires
        self.removed = False

    def __lt__(self, other):
        return self.expires < other.expires


class TLRUCache(_TimedCache):
    """Time-aware LRU cache with per-item TTU function."""

    def __init__(self, maxsize, ttu, timer=time.monotonic, getsizeof=None):
        _TimedCache.__init__(self, maxsize, timer, getsizeof)
        self.__ttu = ttu
        self.__items = {}  # key -> _Item
        self.__order = collections.OrderedDict()
        self.__heap = []

    @property
    def ttu(self):
        return self.__ttu

    def __contains__(self, key):
        try:
            item = self.__items[key]
        except KeyError:
            return False
        return item.expires > self.timer()

    def __getitem__(self, key):
        try:
            item = self.__items[key]
        except KeyError:
            return Cache.__missing__(self, key)
        if item.expires <= self.timer():
            return Cache.__missing__(self, key)
        self.__order.move_to_end(key)
        return Cache._Cache__data.fget(self)[key]

    def __setitem__(self, key, value):
        with self.timer as now:
            expires = self.__ttu(key, value, now)
            if expires <= now:
                # Silently discard
                return
            Cache.__setitem__(self, key, value)
            if key in self.__items:
                self.__items[key].removed = True
            item = _Item(key, expires)
            self.__items[key] = item
            import heapq
            heapq.heappush(self.__heap, item)
            if key in self.__order:
                self.__order.move_to_end(key)
            else:
                self.__order[key] = None

    def __delitem__(self, key):
        Cache.__delitem__(self, key)
        if key in self.__items:
            self.__items[key].removed = True
            del self.__items[key]
        if key in self.__order:
            del self.__order[key]

    def expire(self, time=None):
        import heapq
        if time is None:
            time = self.timer()
        expired = []
        while self.__heap:
            item = self.__heap[0]
            if item.removed:
                heapq.heappop(self.__heap)
                continue
            # Check if this item is still the current item for its key
            current_item = self.__items.get(item.key)
            if current_item is not item:
                item.removed = True
                heapq.heappop(self.__heap)
                continue
            if item.expires <= time:
                heapq.heappop(self.__heap)
                key = item.key
                del self.__items[key]
                if key in self.__order:
                    del self.__order[key]
                try:
                    value = Cache._Cache__data.fget(self)[key]
                    Cache.__delitem__(self, key)
                    expired.append((key, value))
                except KeyError:
                    pass
            else:
                break
        return expired

    def popitem(self):
        with self.timer as now:
            self.expire(now)
            try:
                key = next(iter(self.__order))
            except StopIteration:
                raise KeyError("cache is empty")
            del self.__order[key]
            if key in self.__items:
                self.__items[key].removed = True
                del self.__items[key]
            value = Cache._Cache__data.fget(self)[key]
            Cache.__delitem__(self, key)
            return key, value


def cached(cache, key=None, lock=None, info=False):
    """Memoisation decorator factory."""
    if key is None:
        key = keys.hashkey

    def decorator(func):
        hits = 0
        misses = 0

        if cache is None:
            def wrapper(*args, **kwargs):
                nonlocal misses
                misses += 1
                return func(*args, **kwargs)

        elif lock is None:
            def wrapper(*args, **kwargs):
                nonlocal hits, misses
                k = key(*args, **kwargs)
                try:
                    result = cache[k]
                    hits += 1
                    return result
                except KeyError:
                    pass
                misses += 1
                result = func(*args, **kwargs)
                try:
                    cache[k] = result
                except ValueError:
                    pass  # value too large
                return result

        else:
            def wrapper(*args, **kwargs):
                nonlocal hits, misses
                k = key(*args, **kwargs)
                with lock:
                    try:
                        result = cache[k]
                        hits += 1
                        return result
                    except KeyError:
                        pass
                misses += 1
                result = func(*args, **kwargs)
                with lock:
                    try:
                        cache.setdefault(k, result)
                    except (ValueError, AttributeError):
                        try:
                            cache[k] = result
                        except ValueError:
                            pass
                return result

        import functools
        functools.update_wrapper(wrapper, func)
        wrapper.cache = cache
        wrapper.cache_key = key
        wrapper.cache_lock = lock

        def cache_clear():
            nonlocal hits, misses
            hits = 0
            misses = 0
            if cache is not None:
                if lock is not None:
                    with lock:
                        cache.clear()
                else:
                    cache.clear()

        wrapper.cache_clear = cache_clear

        if info:
            def cache_info():
                if cache is None:
                    return (hits, misses, 0, 0)
                _maxsize = getattr(cache, "maxsize", None)
                import math
                if _maxsize is not None and math.isinf(_maxsize):
                    _maxsize = None
                _currsize = getattr(cache, "currsize", len(cache))
                return (hits, misses, _maxsize, _currsize)
            wrapper.cache_info = cache_info

        return wrapper

    return decorator


def cachedmethod(cache, key=None, lock=None):
    """Instance-method memoisation decorator factory."""
    if key is None:
        key = keys.methodkey

    def decorator(method):
        if lock is None:
            def wrapper(self, *args, **kwargs):
                c = cache(self)
                if c is None:
                    return method(self, *args, **kwargs)
                k = key(self, *args, **kwargs)
                try:
                    return c[k]
                except KeyError:
                    pass
                result = method(self, *args, **kwargs)
                try:
                    c[k] = result
                except ValueError:
                    pass
                return result
        else:
            def wrapper(self, *args, **kwargs):
                c = cache(self)
                if c is None:
                    return method(self, *args, **kwargs)
                k = key(self, *args, **kwargs)
                lk = lock(self)
                with lk:
                    try:
                        return c[k]
                    except KeyError:
                        pass
                result = method(self, *args, **kwargs)
                with lk:
                    try:
                        c.setdefault(k, result)
                    except (ValueError, AttributeError):
                        try:
                            c[k] = result
                        except ValueError:
                            pass
                return result

        import functools
        functools.update_wrapper(wrapper, method)
        wrapper.cache = cache
        wrapper.cache_key = key
        wrapper.cache_lock = lock

        def cache_clear(self):
            c = cache(self)
            if c is not None:
                if lock is not None:
                    lk = lock(self)
                    with lk:
                        c.clear()
                else:
                    c.clear()

        wrapper.cache_clear = cache_clear

        return wrapper

    return decorator
