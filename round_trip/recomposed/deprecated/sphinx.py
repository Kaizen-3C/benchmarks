import re
import textwrap
from . import classic


def _clean_reason(reason):
    if reason is None:
        return None
    # Replace :role:`content` or :domain:role:`content` with `content`
    pattern = r':(?:[A-Za-z0-9_]+:)?[A-Za-z0-9_]+:`([^`]*)`'
    return re.sub(pattern, r'`\1`', reason)


class SphinxAdapter:
    def __init__(self, directive, reason=None, version=None, line_length=70):
        classic._validate_reason(reason)
        self.directive = directive
        self.reason = reason
        self.version = version
        self.line_length = line_length

    def __call__(self, wrapped):
        directive_block = self._build_directive_block()
        if wrapped.__doc__:
            wrapped.__doc__ = wrapped.__doc__.rstrip() + "\n\n" + directive_block
        else:
            wrapped.__doc__ = "\n" + directive_block
        return wrapped

    def _build_directive_block(self):
        version_str = self.version if self.version is not None else ""
        block = ".. %s:: %s" % (self.directive, version_str)
        if self.reason:
            reason_text = textwrap.dedent(self.reason).strip("\n")
            lines = reason_text.splitlines()
            indented_lines = []
            for line in lines:
                stripped = line.strip()
                if not stripped:
                    indented_lines.append("")
                else:
                    if self.line_length and self.line_length > 0:
                        wrapped_lines = textwrap.wrap(stripped, width=self.line_length - 3)
                        for wl in wrapped_lines:
                            indented_lines.append("   " + wl)
                    else:
                        indented_lines.append("   " + stripped)
            if indented_lines:
                block += "\n" + "\n".join(indented_lines)
        return block

    def get_deprecated_msg(self, wrapped, kind=None):
        if kind is None:
            if isinstance(wrapped, type):
                kind = "class"
            else:
                kind = "function (or staticmethod)"
        clean = _clean_reason(self.reason)
        return classic._build_message(kind, wrapped.__name__, reason=clean, version=self.version)


def deprecated(reason=None, version=None, category=DeprecationWarning, action=None, line_length=70, extra_stacklevel=0):
    # Dual-mode decorator
    if (callable(reason) and version is None and category is DeprecationWarning
            and action is None and line_length == 70 and extra_stacklevel == 0):
        # Bare usage: @deprecated
        obj = reason
        reason = None
        adapter = SphinxAdapter("deprecated", reason=reason, version=version, line_length=line_length)
        obj = adapter(obj)
        # Apply runtime warning via classic.deprecated
        clean = _clean_reason(reason)
        obj = classic.deprecated(reason=clean, version=version, category=category,
                                  action=action, extra_stacklevel=extra_stacklevel)(obj)
        return obj
    else:
        classic._validate_reason(reason)

        def decorator(obj):
            adapter = SphinxAdapter("deprecated", reason=reason, version=version, line_length=line_length)
            obj = adapter(obj)
            clean = _clean_reason(reason)
            obj = classic.deprecated(reason=clean, version=version, category=category,
                                      action=action, extra_stacklevel=extra_stacklevel)(obj)
            return obj

        return decorator


def versionadded(reason=None, version=None, line_length=70):
    return SphinxAdapter("versionadded", reason=reason, version=version, line_length=line_length)


def versionchanged(reason=None, version=None, line_length=70):
    return SphinxAdapter("versionchanged", reason=reason, version=version, line_length=line_length)
