"""
Cache key helper functions.
"""

__all__ = ["hashkey", "methodkey", "typedkey", "typedmethodkey"]


class _HashedTuple(tuple):
    """Tuple subclass that caches its hash value."""

    __hashvalue = None

    def __hash__(self, hash=tuple.__hash__):
        hashvalue = self.__dict__.get("hashvalue")
        if hashvalue is None:
            self.__dict__["hashvalue"] = hashvalue = hash(self)
        return hashvalue

    def __add__(self, other):
        return _HashedTuple(tuple.__add__(self, other))

    def __radd__(self, other):
        return _HashedTuple(tuple.__add__(other, self))

    def __getstate__(self):
        return {}

    def __setstate__(self, state):
        pass

    def __getnewargs__(self):
        return (tuple(self),)


class _KWMark:
    """Singleton marker separating positional from keyword arguments."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = object.__new__(cls)
        return cls._instance

    def __reduce__(self):
        return (_kwmark_singleton, ())


def _kwmark_singleton():
    """Factory function to restore the _kwmark singleton after pickling."""
    return _kwmark


_kwmark = _KWMark()


def hashkey(*args, **kwargs):
    """Return a cache key for the given arguments."""
    if kwargs:
        return _HashedTuple(args + (_kwmark,) + tuple(sorted(kwargs.items())))
    return _HashedTuple(args)


def methodkey(self, *args, **kwargs):
    """Return a cache key for the given arguments, dropping self."""
    return hashkey(*args, **kwargs)


def typedkey(*args, **kwargs):
    """Return a typed cache key for the given arguments."""
    key = hashkey(*args, **kwargs)
    # Append types of positional args
    type_suffix = tuple(type(v) for v in args)
    if kwargs:
        type_suffix += tuple(type(v) for _, v in sorted(kwargs.items()))
    return key + type_suffix


def typedmethodkey(self, *args, **kwargs):
    """Return a typed cache key for the given arguments, dropping self."""
    return typedkey(*args, **kwargs)
