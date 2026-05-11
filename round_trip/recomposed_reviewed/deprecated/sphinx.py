import re
import textwrap
from . import classic


def _clean_reason(reason):
    if reason is None:
        return None
    # Replace Sphinx role markup like :func:`foo` or :py:func:`foo` with `foo`
    pattern = r':(?:[A-Za-z0-9_]+:)?(?:[A-Za-z0-9_]+):`([^`]*)`'
    return re.sub(pattern, r'`\1`', reason)


class SphinxAdapter:
    def __init__(self, directive, reason=None, version=None, line_length=70):
        classic._validate_reason(reason)
        self.directive = directive
        self.reason = reason
        self.version = version
        self.line_length = line_length

    def _build_directive_block(self):
        version_str = self.version if self.version is not None else ""
        header = ".. {}:: {}".format(self.directive, version_str)
        lines = [header]

        if self.reason:
            # Dedent and strip leading/trailing newlines
            dedented = textwrap.dedent(self.reason).strip("\n")
            reason_lines = dedented.splitlines()

            for line in reason_lines:
                # Check if line is blank after stripping
                if not line.strip():
                    lines.append("")
                else:
                    # Wrap line to line_length
                    if self.line_length and self.line_length > 0:
                        wrapped = textwrap.wrap(line, width=self.line_length - 3)
                        if wrapped:
                            for wl in wrapped:
                                lines.append("   " + wl)
                        else:
                            lines.append("   " + line)
                    else:
                        lines.append("   " + line)

        return "\n".join(lines)

    def __call__(self, wrapped):
        directive_block = self._build_directive_block()

        if wrapped.__doc__:
            existing = wrapped.__doc__.rstrip()
            wrapped.__doc__ = existing + "\n\n" + directive_block
        else:
            wrapped.__doc__ = "\n" + directive_block

        return wrapped

    def get_deprecated_msg(self, wrapped, kind=None):
        if kind is None:
            if isinstance(wrapped, type):
                kind = "class"
            else:
                kind = "function (or staticmethod)"
        cleaned_reason = _clean_reason(self.reason)
        return classic._build_message(kind, wrapped.__name__, reason=cleaned_reason, version=self.version)


def deprecated(reason=None, version=None, category=DeprecationWarning, action=None, line_length=70, extra_stacklevel=0):
    # Detect bare usage
    if (callable(reason) and version is None and category is DeprecationWarning
            and action is None and line_length == 70 and extra_stacklevel == 0):
        obj = reason
        # Apply docstring injection with no reason/version
        adapter = SphinxAdapter("deprecated", reason=None, version=None, line_length=line_length)
        adapter(obj)
        # Apply classic deprecated for runtime warning
        classic_decorator = classic.deprecated(reason=None, version=None, category=category,
                                               action=action, extra_stacklevel=extra_stacklevel)
        return classic_decorator(obj)

    # Validate reason
    classic._validate_reason(reason)

    def decorator(obj):
        # Inject docstring directive using raw reason
        adapter = SphinxAdapter("deprecated", reason=reason, version=version, line_length=line_length)
        adapter(obj)
        # Apply classic deprecated with cleaned reason for runtime warning
        cleaned = _clean_reason(reason)
        classic_decorator = classic.deprecated(reason=cleaned, version=version, category=category,
                                               action=action, extra_stacklevel=extra_stacklevel)
        return classic_decorator(obj)

    return decorator


def versionadded(reason=None, version=None, line_length=70):
    return SphinxAdapter("versionadded", reason=reason, version=version, line_length=line_length)


def versionchanged(reason=None, version=None, line_length=70):
    return SphinxAdapter("versionchanged", reason=reason, version=version, line_length=line_length)
