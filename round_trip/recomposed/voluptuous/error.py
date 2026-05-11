class Error(Exception):
    """Base class for all voluptuous exceptions."""
    pass


class SchemaError(Error):
    """Raised when a schema definition is invalid."""
    pass


class Invalid(Error):
    """Raised when data fails validation."""

    def __init__(self, message, path=None, error_message=None, error_type=None):
        super().__init__(message)
        self._path = path or []
        self._error_message = error_message or message
        self.error_type = error_type

    @property
    def msg(self):
        return self.args[0]

    @property
    def path(self):
        return self._path

    @path.setter
    def path(self, value):
        self._path = value

    @property
    def error_message(self):
        return self._error_message

    @error_message.setter
    def error_message(self, value):
        self._error_message = value

    def prepend(self, path):
        self._path = list(path) + self._path

    def __str__(self):
        path = ' @ data[%s]' % ']['.join(map(repr, self._path)) if self._path else ''
        output = self.msg
        if self.error_type:
            output = '%s for %s' % (output, self.error_type)
        return output + path

    def __repr__(self):
        return '%s(%r)' % (self.__class__.__name__, self.msg)


class MultipleInvalid(Invalid):
    """Aggregates multiple Invalid errors."""

    def __init__(self, errors=None):
        self.errors = list(errors) if errors else []
        if self.errors:
            super().__init__(self.errors[0].msg, self.errors[0].path,
                             self.errors[0].error_message, self.errors[0].error_type)
        else:
            super().__init__('')

    @property
    def msg(self):
        return self.errors[0].msg if self.errors else ''

    @property
    def path(self):
        return self.errors[0].path if self.errors else []

    @path.setter
    def path(self, value):
        pass  # delegated

    @property
    def error_message(self):
        return self.errors[0].error_message if self.errors else ''

    @error_message.setter
    def error_message(self, value):
        pass  # delegated

    def add(self, error):
        self.errors.append(error)

    def prepend(self, path):
        for error in self.errors:
            error.prepend(path)

    def __str__(self):
        return str(self.errors[0]) if self.errors else ''

    def __repr__(self):
        return 'MultipleInvalid(%r)' % [repr(e) for e in self.errors]


# Leaf exception classes
class RequiredFieldInvalid(Invalid):
    pass

class ObjectInvalid(Invalid):
    pass

class DictInvalid(Invalid):
    pass

class ExclusiveInvalid(Invalid):
    pass

class InclusiveInvalid(Invalid):
    pass

class SequenceTypeInvalid(Invalid):
    pass

class TypeInvalid(Invalid):
    pass

class ValueInvalid(Invalid):
    pass

class ContainsInvalid(Invalid):
    pass

class ScalarInvalid(Invalid):
    pass

class CoerceInvalid(Invalid):
    pass

class AnyInvalid(Invalid):
    pass

class AllInvalid(Invalid):
    pass

class MatchInvalid(Invalid):
    pass

class RangeInvalid(Invalid):
    pass

class TrueInvalid(Invalid):
    pass

class FalseInvalid(Invalid):
    pass

class BooleanInvalid(Invalid):
    pass

class UrlInvalid(Invalid):
    pass

class EmailInvalid(Invalid):
    pass

class FileInvalid(Invalid):
    pass

class DirInvalid(Invalid):
    pass

class PathInvalid(Invalid):
    pass

class LiteralInvalid(Invalid):
    pass

class LengthInvalid(Invalid):
    pass

class DatetimeInvalid(Invalid):
    pass

class DateInvalid(Invalid):
    pass

class InInvalid(Invalid):
    pass

class NotInInvalid(Invalid):
    pass

class ExactSequenceInvalid(Invalid):
    pass

class NotEnoughValid(Invalid):
    pass

class TooManyValid(Invalid):
    pass
