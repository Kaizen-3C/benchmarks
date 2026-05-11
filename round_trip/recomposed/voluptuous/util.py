from voluptuous import validators
from voluptuous.error import Invalid, LiteralInvalid, TypeInvalid
from voluptuous.schema_builder import DefaultFactory, Schema, default_factory, raises


def Lower(v):
    """Convert string to lowercase."""
    return str(v).lower()


def Upper(v):
    """Convert string to uppercase."""
    return str(v).upper()


def Capitalize(v):
    """Capitalize string."""
    return str(v).capitalize()


def Title(v):
    """Title-case string."""
    return str(v).title()


def Strip(v):
    """Strip whitespace from string."""
    return str(v).strip()


class DefaultTo:
    """Return default if value is None."""

    def __init__(self, default_value, msg=None):
        self.default_value = default_factory(default_value)
        self.msg = msg

    def __call__(self, v):
        if v is None:
            return self.default_value()
        return v


class SetTo:
    """Always return a fixed value."""

    def __init__(self, value):
        self.value = default_factory(value)

    def __call__(self, v):
        return self.value()


class Set:
    """Convert to set."""

    def __init__(self, msg=None):
        self.msg = msg

    def __call__(self, v):
        try:
            return set(v)
        except TypeError as e:
            raise TypeInvalid(self.msg or str(e))


class Literal:
    """Validate literal equality."""

    def __init__(self, lit):
        self.lit = lit

    def __call__(self, value, msg=None):
        if self.lit != value:
            raise LiteralInvalid(msg or ('expected %r' % self.lit))
        return self.lit
