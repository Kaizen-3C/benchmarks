import functools
import inspect
import warnings


def _validate_reason(reason):
    if reason is not None and not isinstance(reason, str):
        raise TypeError("reason must be a str or None, not %r" % type(reason))


def _build_message(kind, name, reason=None, version=None):
    msg = "Call to deprecated %s %s." % (kind, name)
    extras = []
    if version is not None:
        extras.append("Deprecated in version %s." % version)
    if reason:
        extras.append(reason)
    if extras:
        msg += " (%s)" % " ".join(extras)
    return msg


def _warn(msg, category, action, stacklevel):
    if action is None:
        warnings.warn(msg, category, stacklevel=stacklevel)
    else:
        with warnings.catch_warnings():
            warnings.simplefilter(action, category)
            warnings.warn(msg, category, stacklevel=stacklevel)


def _kind_for_callable(obj):
    try:
        sig = inspect.signature(obj)
        params = list(sig.parameters.keys())
        if not params:
            return "function (or staticmethod)"
        first = params[0]
        if first == "self":
            return "method"
        elif first == "cls":
            import sys
            if sys.version_info >= (3, 9):
                return "class method"
            else:
                return "function (or staticmethod)"
        else:
            return "function (or staticmethod)"
    except Exception:
        return "function (or staticmethod)"


def _decorate_class(cls, reason, version, category, action, extra_stacklevel):
    msg = _build_message("class", cls.__name__, reason=reason, version=version)
    original_new = cls.__new__

    def wrapped_new(subcls, *args, **kwargs):
        _warn(msg, category, action, stacklevel=3 + int(extra_stacklevel))
        if original_new is object.__new__:
            return object.__new__(subcls)
        else:
            return original_new(subcls, *args, **kwargs)

    cls.__new__ = staticmethod(wrapped_new)
    return cls


def _decorate_callable(func, reason, version, category, action, extra_stacklevel):
    kind = _kind_for_callable(func)
    msg = _build_message(kind, func.__name__, reason=reason, version=version)

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        _warn(msg, category, action, stacklevel=3 + int(extra_stacklevel))
        return func(*args, **kwargs)

    return wrapper


def deprecated(reason=None, version=None, category=DeprecationWarning, action=None, extra_stacklevel=0):
    # Dual-mode: bare decorator or parameterised
    if callable(reason) and version is None and category is DeprecationWarning and action is None and extra_stacklevel == 0:
        # Bare usage: @deprecated
        obj = reason
        reason = None
        if isinstance(obj, type):
            return _decorate_class(obj, reason, version, category, action, extra_stacklevel)
        else:
            return _decorate_callable(obj, reason, version, category, action, extra_stacklevel)
    else:
        # Parameterised usage: @deprecated(...) or validation
        _validate_reason(reason)

        def decorator(obj):
            if isinstance(obj, type):
                return _decorate_class(obj, reason, version, category, action, extra_stacklevel)
            else:
                return _decorate_callable(obj, reason, version, category, action, extra_stacklevel)

        return decorator
