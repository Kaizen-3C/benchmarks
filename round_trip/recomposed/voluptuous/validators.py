import os
import re
import datetime
from decimal import Decimal, InvalidOperation
import collections.abc

from voluptuous.error import (
    AllInvalid, AnyInvalid, BooleanInvalid, CoerceInvalid, ContainsInvalid,
    DateInvalid, DatetimeInvalid, DirInvalid, EmailInvalid, ExactSequenceInvalid,
    FalseInvalid, FileInvalid, InInvalid, Invalid, LengthInvalid, MatchInvalid,
    MultipleInvalid, NotEnoughValid, NotInInvalid, PathInvalid, RangeInvalid,
    TooManyValid, TrueInvalid, TypeInvalid, UrlInvalid
)
from voluptuous.schema_builder import Schema, Schemable if False else None, VirtualPathComponent, message, raises

# Fix import - Schemable is not defined, use Any type hint approach
from voluptuous.schema_builder import Schema, VirtualPathComponent, message, raises

try:
    from enum import Enum
except ImportError:
    Enum = None

import urllib.parse

# Regex patterns for URL and email validation
USER_REGEX = re.compile(
    r"(^[-!#$%&'*+/=?^_`{}|~0-9A-Z]+(\.[-!#$%&'*+/=?^_`{}|~0-9A-Z]+)*$"  # dot-atom
    r'|^"([\001-\010\013\014\016-\037!#-\[\]-\177]|\\[\001-\011\013\014\016-\177])*"$)',  # quoted-string
    re.IGNORECASE
)

DOMAIN_REGEX = re.compile(
    r'(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)$'
    r'|^\[?[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\]?',
    re.IGNORECASE
)


def truth(f):
    """Decorator that raises Invalid if f returns falsy."""
    from functools import wraps

    @wraps(f)
    def wrapper(*args, **kwargs):
        result = f(*args, **kwargs)
        if not result:
            raise Invalid('not a valid value')
        return result

    return wrapper


class Coerce:
    """Coerce a value to a type."""

    def __init__(self, type, msg=None):
        self.type = type
        self.msg = msg
        self.type_name = getattr(type, '__name__', str(type))

    def __call__(self, v):
        try:
            return self.type(v)
        except (ValueError, TypeError, InvalidOperation) as e:
            msg = self.msg
            if msg is None:
                if Enum is not None and isinstance(self.type, type) and issubclass(self.type, Enum):
                    choices = ', '.join(str(m.value) for m in self.type)
                    msg = 'expected %s or one of %s' % (self.type_name, choices)
                else:
                    msg = 'expected %s' % self.type_name
            raise CoerceInvalid(msg)


@message('value was not true', cls=TrueInvalid)
@truth
def IsTrue(v):
    """Validate that value is truthy."""
    return v


def IsFalse(v):
    """Validate that value is falsy."""
    if v:
        raise FalseInvalid('value was not false')
    return v


def Boolean(v):
    """Convert value to boolean."""
    if isinstance(v, str):
        v_lower = v.lower()
        if v_lower in ('1', 'true', 'yes', 'on', 'enable'):
            return True
        elif v_lower in ('0', 'false', 'no', 'off', 'disable'):
            return False
        else:
            raise BooleanInvalid('expected boolean')
    return bool(v)


class _WithSubValidators:
    """Base class for validators that combine sub-validators."""

    def __init__(self, *validators, **kwargs):
        self.validators = validators
        self.msg = kwargs.get('msg', None)
        self._compiled = None

    def __voluptuous_compile__(self, schema):
        """Hook called during schema compilation."""
        self._schema = schema
        self._compiled_validators = []
        for v in self.validators:
            # Temporarily compile each validator
            old_required = schema.required
            compiled = schema._compile(v)
            self._compiled_validators.append(compiled)
        return self._run_compiled

    def _run_compiled(self, path, value):
        return self._exec(self._compiled_validators, path, value)

    def __call__(self, v):
        """Standalone call - wrap each validator in Schema."""
        compiled = [Schema(val)._compiled for val in self.validators]
        return self._exec(compiled, [], v)

    def _exec(self, validators, path, value):
        raise NotImplementedError


class Any(_WithSubValidators):
    """Return first passing validator result."""

    def __init__(self, *validators, **kwargs):
        self.discriminant = kwargs.pop('discriminant', None)
        super().__init__(*validators, **kwargs)

    def __voluptuous_compile__(self, schema):
        self._schema = schema
        self._compiled_validators = []
        for v in self.validators:
            compiled = schema._compile(v)
            self._compiled_validators.append(compiled)
        return self._run_compiled

    def _run_compiled(self, path, value):
        validators = self._compiled_validators
        if self.discriminant is not None:
            validators = list(self.discriminant(value, validators))

        error = None
        for compiled in validators:
            try:
                return compiled(path, value)
            except Invalid as e:
                if error is None or len(e.path) > len(error.path):
                    error = e

        if self.msg:
            raise AnyInvalid(self.msg, path)
        elif error:
            raise AnyInvalid(error.msg, path) if not error.path or error.path == path else error
        else:
            raise AnyInvalid('no valid value', path)

    def _exec(self, validators, path, value):
        error = None
        for compiled in validators:
            try:
                return compiled(path, value)
            except Invalid as e:
                if error is None or len(e.path) > len(error.path):
                    error = e

        if self.msg:
            raise AnyInvalid(self.msg, path)
        elif error:
            raise AnyInvalid(error.msg, path)
        else:
            raise AnyInvalid('no valid value', path)

    def __call__(self, v):
        schema_validators = [Schema(val)._compiled for val in self.validators]
        return self._exec(schema_validators, [], v)


Or = Any


class All(_WithSubValidators):
    """Chain validators, passing result of each to next."""

    def __voluptuous_compile__(self, schema):
        self._schema = schema
        self._compiled_validators = []
        for v in self.validators:
            compiled = schema._compile(v)
            self._compiled_validators.append(compiled)
        return self._run_compiled

    def _run_compiled(self, path, value):
        for compiled in self._compiled_validators:
            try:
                value = compiled(path, value)
            except Invalid as e:
                if self.msg:
                    raise AllInvalid(self.msg, path)
                raise
        return value

    def _exec(self, validators, path, value):
        for compiled in validators:
            try:
                value = compiled(path, value)
            except Invalid as e:
                if self.msg:
                    raise AllInvalid(self.msg, path)
                raise
        return value

    def __call__(self, v):
        schema_validators = [Schema(val)._compiled for val in self.validators]
        return self._exec(schema_validators, [], v)


And = All


class Union(_WithSubValidators):
    """Like Any but with optional discriminant."""

    def __init__(self, *validators, **kwargs):
        self.discriminant = kwargs.pop('discriminant', None)
        super().__init__(*validators, **kwargs)

    def __voluptuous_compile__(self, schema):
        self._schema = schema
        self._compiled_validators = []
        for v in self.validators:
            compiled = schema._compile(v)
            self._compiled_validators.append(compiled)
        return self._run_compiled

    def _run_compiled(self, path, value):
        validators = self._compiled_validators
        if self.discriminant is not None:
            validators = list(self.discriminant(value, validators))

        error = None
        for compiled in validators:
            try:
                return compiled(path, value)
            except Invalid as e:
                if error is None or len(e.path) > len(error.path):
                    error = e

        if self.msg:
            raise AnyInvalid(self.msg, path)
        elif error:
            raise AnyInvalid(error.msg, path)
        else:
            raise AnyInvalid('no valid value', path)

    def _exec(self, validators, path, value):
        return Any._exec(self, validators, path, value)

    def __call__(self, v):
        schema_validators = [Schema(val)._compiled for val in self.validators]
        return self._exec(schema_validators, [], v)


Switch = Union


class SomeOf(_WithSubValidators):
    """Require some validators to pass."""

    def __init__(self, validators, min_valid=None, max_valid=None, msg=None):
        self.validators = validators
        self.min_valid = min_valid
        self.max_valid = max_valid
        self.msg = msg

    def __voluptuous_compile__(self, schema):
        self._schema = schema
        self._compiled_validators = []
        for v in self.validators:
            compiled = schema._compile(v)
            self._compiled_validators.append(compiled)
        return self._run_compiled

    def _run_compiled(self, path, value):
        valid_count = 0
        errors = []
        for compiled in self._compiled_validators:
            try:
                compiled(path, value)
                valid_count += 1
            except Invalid as e:
                errors.append(e)

        if self.min_valid is not None and valid_count < self.min_valid:
            raise NotEnoughValid(
                self.msg or 'Not enough valid values',
                path
            )
        if self.max_valid is not None and valid_count > self.max_valid:
            raise TooManyValid(
                self.msg or 'Too many valid values',
                path
            )
        return value

    def _exec(self, validators, path, value):
        valid_count = 0
        for compiled in validators:
            try:
                compiled(path, value)
                valid_count += 1
            except Invalid:
                pass

        if self.min_valid is not None and valid_count < self.min_valid:
            raise NotEnoughValid(self.msg or 'Not enough valid values', path)
        if self.max_valid is not None and valid_count > self.max_valid:
            raise TooManyValid(self.msg or 'Too many valid values', path)
        return value

    def __call__(self, v):
        schema_validators = [Schema(val)._compiled for val in self.validators]
        return self._exec(schema_validators, [], v)


class Match:
    """Validate using regex match."""

    def __init__(self, pattern, msg=None):
        if isinstance(pattern, str):
            self.pattern = re.compile(pattern)
        else:
            self.pattern = pattern
        self.msg = msg

    def __call__(self, v):
        try:
            if not self.pattern.match(v):
                raise MatchInvalid(self.msg or 'does not match regular expression')
        except TypeError:
            raise MatchInvalid(self.msg or 'expected string or bytes-like object')
        return v


class Replace:
    """Replace using regex substitution."""

    def __init__(self, pattern, substitution, msg=None):
        if isinstance(pattern, str):
            self.pattern = re.compile(pattern)
        else:
            self.pattern = pattern
        self.substitution = substitution
        self.msg = msg

    def __call__(self, v):
        return self.pattern.sub(self.substitution, v)


@message('Not a valid email address', cls=EmailInvalid)
def Email(v):
    """Validate email address."""
    if not v or '@' not in v:
        raise EmailInvalid('Not a valid email address')
    user, domain = v.rsplit('@', 1)
    if not USER_REGEX.match(user):
        raise EmailInvalid('Not a valid email address')
    if not DOMAIN_REGEX.match(domain):
        raise EmailInvalid('Not a valid email address')
    return v


@message('Not a valid URL', cls=UrlInvalid)
def Url(v):
    """Validate URL."""
    try:
        parsed = urllib.parse.urlparse(v)
        if not parsed.scheme or not parsed.netloc:
            raise UrlInvalid('Not a valid URL')
    except Exception:
        raise UrlInvalid('Not a valid URL')
    return v


@message('Not a valid fully qualified domain URL', cls=UrlInvalid)
def FqdnUrl(v):
    """Validate fully qualified domain URL."""
    try:
        parsed = urllib.parse.urlparse(v)
        if not parsed.scheme or not parsed.netloc:
            raise UrlInvalid('Not a valid fully qualified domain URL')
        # Get netloc without port
        netloc = parsed.netloc
        if ':' in netloc:
            netloc = netloc.rsplit(':', 1)[0]
        if not DOMAIN_REGEX.match(netloc):
            raise UrlInvalid('Not a valid fully qualified domain URL')
    except UrlInvalid:
        raise
    except Exception:
        raise UrlInvalid('Not a valid fully qualified domain URL')
    return v


def IsFile(v):
    """Validate that path is a file."""
    if not os.path.isfile(v):
        raise FileInvalid('not a file')
    return v


def IsDir(v):
    """Validate that path is a directory."""
    if not os.path.isdir(v):
        raise DirInvalid('not a directory')
    return v


def PathExists(v):
    """Validate that path exists."""
    if v is None or not os.path.exists(v):
        raise PathInvalid('path does not exist')
    return v


def Maybe(validator, msg=None):
    """Accept None or pass validator."""
    return Any(None, validator, msg=msg)


class Range:
    """Validate numeric range."""

    def __init__(self, min=None, max=None, min_included=True, max_included=True, msg=None):
        self.min = min
        self.max = max
        self.min_included = min_included
        self.max_included = max_included
        self.msg = msg

    def __call__(self, v):
        try:
            # Check for NaN
            if v != v:  # NaN check
                raise RangeInvalid(self.msg or 'value is not a number')
        except TypeError:
            pass

        try:
            if self.min is not None:
                if self.min_included:
                    if v < self.min:
                        raise RangeInvalid(
                            self.msg or 'value must be at least %s' % self.min
                        )
                else:
                    if v <= self.min:
                        raise RangeInvalid(
                            self.msg or 'value must be higher than %s' % self.min
                        )
            if self.max is not None:
                if self.max_included:
                    if v > self.max:
                        raise RangeInvalid(
                            self.msg or 'value must be at most %s' % self.max
                        )
                else:
                    if v >= self.max:
                        raise RangeInvalid(
                            self.msg or 'value must be lower than %s' % self.max
                        )
        except TypeError:
            raise RangeInvalid(self.msg or 'invalid value')

        return v


class Clamp:
    """Clamp value to range."""

    def __init__(self, min=None, max=None, msg=None):
        self.min = min
        self.max = max
        self.msg = msg

    def __call__(self, v):
        try:
            if self.min is not None and v < self.min:
                v = self.min
            if self.max is not None and v > self.max:
                v = self.max
        except TypeError:
            raise RangeInvalid(self.msg or 'invalid value')
        return v


class Length:
    """Validate length of a value."""

    def __init__(self, min=None, max=None, msg=None):
        self.min = min
        self.max = max
        self.msg = msg

    def __call__(self, v):
        try:
            length = len(v)
        except TypeError:
            raise RangeInvalid(self.msg or 'value has no length')

        if self.min is not None and length < self.min:
            raise LengthInvalid(
                self.msg or 'length of value must be at least %d' % self.min
            )
        if self.max is not None and length > self.max:
            raise LengthInvalid(
                self.msg or 'length of value must be at most %d' % self.max
            )
        return v


class Datetime:
    """Validate datetime string."""

    DEFAULT_FORMAT = '%Y-%m-%dT%H:%M:%S.%fZ'

    def __init__(self, format=None, msg=None):
        self.format = format or self.DEFAULT_FORMAT
        self.msg = msg

    def __call__(self, v):
        try:
            datetime.datetime.strptime(v, self.format)
        except (ValueError, TypeError):
            raise DatetimeInvalid(
                self.msg or 'expected datetime %s' % self.format
            )
        return v


class Date:
    """Validate date string."""

    DEFAULT_FORMAT = '%Y-%m-%d'

    def __init__(self, format=None, msg=None):
        self.format = format or self.DEFAULT_FORMAT
        self.msg = msg

    def __call__(self, v):
        try:
            datetime.datetime.strptime(v, self.format)
        except (ValueError, TypeError):
            raise DateInvalid(
                self.msg or 'expected date %s' % self.format
            )
        return v


class In:
    """Validate value is in container."""

    def __init__(self, container, msg=None):
        self.container = container
        self.msg = msg

    def __call__(self, v):
        if v not in self.container:
            raise InInvalid(self.msg or 'value is not allowed')
        return v


class NotIn:
    """Validate value is not in container."""

    def __init__(self, container, msg=None):
        self.container = container
        self.msg = msg

    def __call__(self, v):
        if v in self.container:
            raise NotInInvalid(self.msg or 'value is not allowed')
        return v


class Contains:
    """Validate container contains item."""

    def __init__(self, item, msg=None):
        self.item = item
        self.msg = msg

    def __call__(self, v):
        if self.item not in v:
            raise ContainsInvalid(self.msg or 'value does not contain required item')
        return v


class ExactSequence:
    """Validate sequence with exact positional validators."""

    def __init__(self, validators, msg=None, **kwargs):
        self.validators = validators
        self.msg = msg

    def __call__(self, v):
        if not isinstance(v, (list, tuple)):
            raise ExactSequenceInvalid(self.msg or 'expected a list or tuple')

        if len(v) != len(self.validators):
            raise ExactSequenceInvalid(
                self.msg or 'wrong number of elements'
            )

        output = []
        errors = []
        for i, (item, validator) in enumerate(zip(v, self.validators)):
            try:
                new_val = Schema(validator)(item)
                output.append(new_val)
            except (Invalid, Exception) as e:
                if isinstance(e, Invalid):
                    errors.append(e)
                else:
                    errors.append(Invalid(str(e), [i]))

        if errors:
            raise MultipleInvalid(errors)

        return output

    def __voluptuous_compile__(self, schema):
        self._schema = schema
        self._compiled_validators = [schema._compile(v) for v in self.validators]
        return self._run_compiled

    def _run_compiled(self, path, v):
        if not isinstance(v, (list, tuple)):
            raise ExactSequenceInvalid(self.msg or 'expected a list or tuple', path)

        if len(v) != len(self._compiled_validators):
            raise ExactSequenceInvalid(
                self.msg or 'wrong number of elements', path
            )

        output = []
        errors = []
        for i, (item, compiled) in enumerate(zip(v, self._compiled_validators)):
            try:
                new_val = compiled(path + [i], item)
                output.append(new_val)
            except Invalid as e:
                errors.append(e)

        if errors:
            raise MultipleInvalid(errors)

        return output


class Unique:
    """Validate all elements are unique."""

    def __init__(self, msg=None):
        self.msg = msg

    def __call__(self, v):
        try:
            if len(set(v)) != len(list(v)):
                raise Invalid(self.msg or 'contains duplicate values')
        except TypeError:
            raise TypeInvalid(self.msg or 'contains unhashable elements')
        return v


class Equal:
    """Validate value equals target."""

    def __init__(self, target, msg=None):
        self.target = target
        self.msg = msg

    def __call__(self, v):
        if v != self.target:
            raise Invalid(self.msg or 'expected %r' % self.target)
        return v


class Unordered:
    """Validate each element matches at least one unused validator."""

    def __init__(self, validators, msg=None, **kwargs):
        self.validators = validators
        self.msg = msg

    def __call__(self, v):
        data = list(v)
        validators = list(self.validators)

        if len(data) != len(validators):
            raise Invalid(self.msg or 'wrong number of elements')

        compiled = [Schema(val)._compiled for val in validators]
        used = [False] * len(compiled)
        output = list(data)

        for i, item in enumerate(data):
            matched = False
            for j, (val_compiled, is_used) in enumerate(zip(compiled, used)):
                if not is_used:
                    try:
                        result = val_compiled([], item)
                        output[i] = result
                        used[j] = True
                        matched = True
                        break
                    except Invalid:
                        pass
            if not matched:
                raise Invalid(self.msg or 'invalid element')

        return output

    def __voluptuous_compile__(self, schema):
        self._schema = schema
        self._compiled_validators = [schema._compile(v) for v in self.validators]
        return self._run_compiled

    def _run_compiled(self, path, v):
        data = list(v)
        compiled = self._compiled_validators

        if len(data) != len(compiled):
            raise Invalid(self.msg or 'wrong number of elements', path)

        used = [False] * len(compiled)
        output = list(data)

        for i, item in enumerate(data):
            matched = False
            for j, (val_compiled, is_used) in enumerate(zip(compiled, used)):
                if not is_used:
                    try:
                        result = val_compiled(path + [i], item)
                        output[i] = result
                        used[j] = True
                        matched = True
                        break
                    except Invalid:
                        pass
            if not matched:
                raise Invalid(self.msg or 'invalid element', path + [i])

        return output


class Number:
    """Validate number precision and scale."""

    def __init__(self, precision=None, scale=None, msg=None, yield_decimal=False):
        self.precision = precision
        self.scale = scale
        self.msg = msg
        self.yield_decimal = yield_decimal

    def __call__(self, v):
        try:
            d = Decimal(str(v))
        except InvalidOperation:
            raise Invalid(self.msg or 'not a valid number')

        sign, digits, exponent = d.as_tuple()

        if exponent >= 0:
            computed_scale = 0
            computed_precision = len(digits) + exponent
        else:
            computed_scale = -exponent
            computed_precision = len(digits)

        errors = []
        if self.precision is not None and computed_precision != self.precision:
            errors.append('precision')
        if self.scale is not None and computed_scale != self.scale:
            errors.append('scale')

        if errors:
            if len(errors) == 2:
                msg = self.msg or ('precision and scale must be %d and %d respectively' %
                                   (self.precision, self.scale))
            elif 'precision' in errors:
                msg = self.msg or ('precision must be %d' % self.precision)
            else:
                msg = self.msg or ('scale must be %d' % self.scale)
            raise Invalid(msg)

        if self.yield_decimal:
            return d
        return v
