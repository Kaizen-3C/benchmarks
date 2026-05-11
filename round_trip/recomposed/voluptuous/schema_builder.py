import collections.abc
import inspect
import sys
from functools import wraps

from voluptuous import error as er
from voluptuous.error import Error


class _Undefined:
    """Singleton undefined sentinel."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __bool__(self):
        return False

    def __repr__(self):
        return '...'

    def __str__(self):
        return '...'


UNDEFINED = _Undefined()
Undefined = _Undefined


def default_factory(value):
    """Create a default factory from a value."""
    if value is UNDEFINED:
        return UNDEFINED
    if callable(value) and not isinstance(value, _Undefined):
        return value
    return lambda: value


class DefaultFactory:
    """Wrapper for default factory callables."""
    def __init__(self, factory):
        self.factory = factory

    def __call__(self):
        return self.factory()


def Extra(_):
    """Sentinel for extra keys."""
    return None


extra = Extra

Self = object()  # sentinel for recursive schemas

PREVENT_EXTRA = 0
ALLOW_EXTRA = 1
REMOVE_EXTRA = 2


class VirtualPathComponent(str):
    """A path component that doesn't correspond to actual data."""

    def __str__(self):
        return '<' + self + '>'

    def __repr__(self):
        return self.__str__()


class Marker:
    """Base class for schema key markers."""

    __slots__ = ('schema', '_schema', 'msg', 'description')

    def __init__(self, schema_, msg=None, description=None):
        self.schema = schema_
        self._schema = schema_
        self.msg = msg
        self.description = description

    def __call__(self, v):
        if isinstance(self._schema, Schema):
            schema = self._schema
        else:
            schema = Schema(self._schema)
        try:
            return schema(v)
        except er.Invalid as e:
            if self.msg and len(e.path) <= 1:
                raise er.Invalid(self.msg)
            raise

    def __repr__(self):
        return '%s(%r)' % (self.__class__.__name__, self.schema)

    def __lt__(self, other):
        if isinstance(other, Marker):
            return self.schema < other.schema
        return self.schema < other

    def __hash__(self):
        return hash(self.schema)

    def __eq__(self, other):
        if isinstance(other, Marker):
            return self.schema == other.schema
        return self.schema == other

    def __str__(self):
        return str(self.schema)


class Required(Marker):
    """A required schema key."""

    __slots__ = ('schema', '_schema', 'msg', 'description', 'default')

    def __init__(self, schema_, msg=None, description=None, default=UNDEFINED):
        super().__init__(schema_, msg=msg, description=description)
        self.default = default_factory(default)


class Optional(Marker):
    """An optional schema key."""

    __slots__ = ('schema', '_schema', 'msg', 'description', 'default')

    def __init__(self, schema_, msg=None, description=None, default=UNDEFINED):
        super().__init__(schema_, msg=msg, description=description)
        self.default = default_factory(default)


class Exclusive(Marker):
    """A key that is mutually exclusive with others in the same group."""

    __slots__ = ('schema', '_schema', 'msg', 'description', 'group_of_exclusion')

    def __init__(self, schema_, group_of_exclusion, msg=None, description=None):
        super().__init__(schema_, msg=msg, description=description)
        self.group_of_exclusion = group_of_exclusion


class Inclusive(Marker):
    """A key that must appear with all others in the same group."""

    __slots__ = ('schema', '_schema', 'msg', 'description', 'group_of_inclusion')

    def __init__(self, schema_, group_of_inclusion, msg=None, description=None):
        super().__init__(schema_, msg=msg, description=description)
        self.group_of_inclusion = group_of_inclusion


class Remove(Marker):
    """A key that should be removed from output if it validates."""

    __slots__ = ('schema', '_schema', 'msg', 'description')

    def __init__(self, schema_):
        super().__init__(schema_)


class Object(dict):
    """Schema for validating Python objects by attribute."""

    def __init__(self, schema, cls=UNDEFINED):
        super().__init__(schema)
        self.cls = cls


class Msg:
    """Wraps a schema and replaces error messages."""

    def __init__(self, schema, msg, cls=None):
        self.schema = schema
        self.msg = msg
        self.cls = cls

    def __call__(self, v):
        try:
            return Schema(self.schema)(v)
        except er.Invalid as e:
            if len(e.path) <= 1:
                raise (self.cls or er.Invalid)(self.msg)
            raise

    def __voluptuous_compile__(self, schema):
        self._compiled_schema = schema._compile(self.schema)
        return self._call_compiled

    def _call_compiled(self, path, v):
        try:
            return self._compiled_schema(path, v)
        except er.Invalid as e:
            if len(e.path) - len(path) <= 1:
                raise (self.cls or er.Invalid)(self.msg, path)
            raise


def message(msg, cls=None):
    """Decorator factory that replaces Invalid messages."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            try:
                return f(*args, **kwargs)
            except er.Invalid as e:
                if len(e.path) <= 1:
                    raise (cls or er.Invalid)(msg)
                raise
        return wrapper
    return decorator


def raises(exc, msg=None, cls=None):
    """Decorator factory that catches exc and re-raises as Invalid."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            try:
                return f(*args, **kwargs)
            except exc as e:
                raise (cls or er.Invalid)(msg or str(e))
        return wrapper
    return decorator


def validate(*args, **kwargs):
    """Decorator factory that validates function arguments and return value."""
    def decorator(func):
        sig = inspect.signature(func)
        params = list(sig.parameters.keys())

        # Build argument schemas
        arg_schemas = {}
        for i, arg in enumerate(args):
            if i < len(params):
                arg_schemas[params[i]] = Schema(arg)

        for key, val in kwargs.items():
            if key != '__return__':
                arg_schemas[key] = Schema(val)

        return_schema = Schema(kwargs['__return__']) if '__return__' in kwargs else None

        @wraps(func)
        def wrapper(*call_args, **call_kwargs):
            bound = sig.bind(*call_args, **call_kwargs)
            bound.apply_defaults()
            for param_name, value in bound.arguments.items():
                if param_name in arg_schemas:
                    bound.arguments[param_name] = arg_schemas[param_name](value)
            result = func(*bound.args, **bound.kwargs)
            if return_schema is not None:
                result = return_schema(result)
            return result

        return wrapper
    return decorator


def _compile_itemsort(item):
    """Sort key for schema items."""
    key = item[0]
    if isinstance(key, Remove):
        return (0, 0, str(key))
    if isinstance(key, Marker):
        inner = key.schema
    else:
        inner = key
    if inner is Extra:
        return (4, 0, str(key))
    if isinstance(inner, type) or callable(inner) and not isinstance(inner, type) and _is_generic(inner):
        if isinstance(inner, type):
            return (2, 0, str(key))
        return (3, 0, str(key))
    return (1, 0, str(key))


def _is_generic(v):
    """Check if value is a callable (but not a type) that serves as a validator."""
    return callable(v) and not isinstance(v, type)


class Schema:
    """A schema validator."""

    def __init__(self, schema, required=False, extra=PREVENT_EXTRA):
        self.schema = schema
        self.required = required
        self.extra = extra
        self._compiled = self._compile(schema)

    def _compile(self, schema):
        """Compile schema into a callable(path, data) -> data."""
        if hasattr(schema, '__voluptuous_compile__'):
            return schema.__voluptuous_compile__(self)

        if schema is Extra:
            return lambda path, data: data

        if schema is Self:
            return lambda path, data: self._compiled(path, data)

        if isinstance(schema, Marker):
            return self._compile_marker(schema)

        if isinstance(schema, Schema):
            return schema._compiled

        if isinstance(schema, Object):
            return self._compile_object(schema)

        if isinstance(schema, collections.abc.Mapping):
            return self._compile_dict(schema)

        if isinstance(schema, list):
            return self._compile_list(schema)

        if isinstance(schema, tuple):
            return self._compile_tuple(schema)

        if isinstance(schema, (set, frozenset)):
            return self._compile_set(schema)

        return self._compile_scalar(schema)

    def _compile_marker(self, marker):
        """Compile a Marker's inner schema."""
        inner_compiled = self._compile(marker.schema)

        def validate_marker(path, data):
            return inner_compiled(path, data)

        return validate_marker

    def _compile_scalar(self, schema):
        """Compile a scalar schema."""
        if isinstance(schema, type):
            def validate_type(path, data):
                if isinstance(data, schema):
                    return data
                else:
                    msg = 'expected %s' % schema.__name__
                    raise er.TypeInvalid(msg, path)
            return validate_type

        if callable(schema):
            def validate_callable(path, data):
                try:
                    return schema(data)
                except er.Invalid as e:
                    raise e.prepend(path) or e
                except ValueError as e:
                    raise er.ValueInvalid('not a valid value', path) from e
                except TypeError as e:
                    raise er.TypeInvalid('not a valid value', path) from e
            return validate_callable

        # Literal value
        def validate_literal(path, data):
            if type(data) == type(schema) and data == schema:
                return data
            elif not isinstance(schema, (bool, int, float, complex, str, bytes)) and data == schema:
                return data
            else:
                if type(schema) in (bool, int, float, str, bytes, type(None)):
                    pass
                msg = 'expected %r' % schema
                raise er.LiteralInvalid(msg, path)  # use ScalarInvalid for general
        return validate_literal

    def _compile_scalar_literal(self, schema):
        """Compile literal equality check."""
        def validate(path, data):
            if data != schema:
                raise er.ScalarInvalid('expected %r' % schema, path)
            if type(data) != type(schema) and isinstance(schema, (bool, int, float, str, bytes, type(None))):
                raise er.ScalarInvalid('expected %r' % schema, path)
            return data
        return validate

    def _compile_dict(self, schema):
        """Compile a dict schema."""
        # Sort schema items
        schema_items = sorted(schema.items(), key=_compile_itemsort)

        # Separate into categories
        required_keys = []
        optional_keys = []

        for skey, svalue in schema_items:
            if isinstance(skey, Required):
                required_keys.append((skey, svalue))
            elif isinstance(skey, Optional):
                optional_keys.append((skey, svalue))
            elif isinstance(skey, Exclusive):
                optional_keys.append((skey, svalue))
            elif isinstance(skey, Inclusive):
                optional_keys.append((skey, svalue))
            elif isinstance(skey, Remove):
                optional_keys.append((skey, svalue))
            elif skey is Extra:
                optional_keys.append((skey, svalue))
            else:
                # bare key
                if self.required:
                    required_keys.append((Required(skey), svalue))
                else:
                    optional_keys.append((Optional(skey), svalue))

        all_schema_keys = required_keys + optional_keys

        def validate_dict(path, data):
            if not isinstance(data, dict):
                raise er.DictInvalid('expected a dictionary', path)

            errors = []
            output = {}
            found_keys = set()

            # Track exclusion groups: group_name -> list of present keys
            exclusion_groups = {}
            # Track inclusion groups: group_name -> (present_keys, all_keys, defaults)
            inclusion_groups = {}

            # Build a mapping from schema key identity to (marker, compiled_value)
            # We'll iterate data keys and match them

            # First, build compiled validators for each schema key
            compiled_schema = []
            for skey, svalue in all_schema_keys:
                compiled_val = self._compile(svalue)
                compiled_schema.append((skey, svalue, compiled_val))

            # Build inclusion group tracking
            for skey, svalue, compiled_val in compiled_schema:
                if isinstance(skey, Inclusive):
                    group = skey.group_of_inclusion
                    if group not in inclusion_groups:
                        inclusion_groups[group] = {'present': [], 'all_markers': [], 'missing': []}
                    inclusion_groups[group]['all_markers'].append(skey)

            # Process data keys
            data_keys = set(data.keys())
            schema_matched_keys = set()  # data keys matched by schema

            # First pass: match specific (literal) schema keys
            for skey, svalue, compiled_val in compiled_schema:
                if isinstance(skey, Marker):
                    inner_key = skey.schema
                else:
                    inner_key = skey

                # Skip type/callable/Extra keys for now
                if isinstance(skey, Remove):
                    if inner_key in data_keys:
                        val = data[inner_key]
                        try:
                            compiled_val(path + [inner_key], val)
                            # Validated, remove it
                            schema_matched_keys.add(inner_key)
                        except er.Invalid:
                            pass  # leave for other handlers
                    continue

                if inner_key is Extra:
                    continue

                if isinstance(inner_key, type) or (callable(inner_key) and not isinstance(inner_key, type)):
                    continue

                # Literal key
                if inner_key in data_keys:
                    val = data[inner_key]
                    try:
                        new_val = compiled_val(path + [inner_key], val)
                        if isinstance(skey, Exclusive):
                            group = skey.group_of_exclusion
                            if group not in exclusion_groups:
                                exclusion_groups[group] = []
                            exclusion_groups[group].append(inner_key)
                        if isinstance(skey, Inclusive):
                            group = skey.group_of_inclusion
                            inclusion_groups[group]['present'].append(inner_key)
                        output[inner_key] = new_val
                        schema_matched_keys.add(inner_key)
                    except er.Invalid as e:
                        errors.append(e)
                        schema_matched_keys.add(inner_key)
                else:
                    # Key not in data
                    if isinstance(skey, Required):
                        if skey.default is not UNDEFINED:
                            output[inner_key] = skey.default()
                        else:
                            errors.append(er.RequiredFieldInvalid(
                                'required key not provided @ data[%s]' % repr(inner_key),
                                path + [inner_key]
                            ))
                    elif isinstance(skey, Optional):
                        if skey.default is not UNDEFINED:
                            output[inner_key] = skey.default()
                    elif isinstance(skey, Inclusive):
                        group = skey.group_of_inclusion
                        inclusion_groups[group]['missing'].append(inner_key)

            # Second pass: handle type/callable schema keys for unmatched data keys
            remaining_keys = data_keys - schema_matched_keys

            for skey, svalue, compiled_val in compiled_schema:
                if isinstance(skey, Marker):
                    inner_key = skey.schema
                else:
                    inner_key = skey

                if inner_key is Extra or isinstance(skey, Remove):
                    continue

                if not (isinstance(inner_key, type) or (callable(inner_key) and not isinstance(inner_key, type))):
                    continue

                # Generic key (type or callable)
                matched_in_pass = set()
                for dk in list(remaining_keys):
                    try:
                        # Validate the key itself
                        if isinstance(inner_key, type):
                            if not isinstance(dk, inner_key):
                                continue
                        elif callable(inner_key):
                            try:
                                inner_key(dk)
                            except Exception:
                                continue

                        val = data[dk]
                        new_val = compiled_val(path + [dk], val)
                        output[dk] = new_val
                        matched_in_pass.add(dk)
                    except er.Invalid as e:
                        errors.append(e)
                        matched_in_pass.add(dk)

                remaining_keys -= matched_in_pass
                schema_matched_keys |= matched_in_pass

            # Handle Extra keys
            remaining_after_generic = data_keys - schema_matched_keys

            # Check for Extra sentinel in schema
            extra_validator = None
            extra_marker = None
            for skey, svalue, compiled_val in compiled_schema:
                if isinstance(skey, Marker):
                    inner = skey.schema
                else:
                    inner = skey
                if inner is Extra:
                    extra_validator = compiled_val
                    extra_marker = skey
                    break

            for dk in remaining_after_generic:
                if extra_validator is not None:
                    val = data[dk]
                    try:
                        new_val = extra_validator(path + [dk], val)
                        output[dk] = new_val
                    except er.Invalid as e:
                        errors.append(e)
                elif self.extra == ALLOW_EXTRA:
                    output[dk] = data[dk]
                elif self.extra == REMOVE_EXTRA:
                    pass  # drop
                else:  # PREVENT_EXTRA
                    errors.append(er.Invalid('extra keys not allowed', path + [dk]))

            # Check exclusion groups
            for group, present in exclusion_groups.items():
                if len(present) > 1:
                    # Find the marker for this group to get msg
                    group_msg = None
                    for skey, svalue, compiled_val in compiled_schema:
                        if isinstance(skey, Exclusive) and skey.group_of_exclusion == group:
                            group_msg = skey.msg
                            break
                    msg = group_msg or ('two or more values in the same group of exclusion \'%s\'' % group)
                    errors.append(er.ExclusiveInvalid(
                        msg, path + [VirtualPathComponent(group)]
                    ))
                    # Remove the conflicting keys from output
                    for k in present:
                        output.pop(k, None)

            # Check inclusion groups
            for group, info in inclusion_groups.items():
                present = info['present']
                missing = info['missing']
                all_markers = info['all_markers']
                if present and missing:
                    # Some present, some missing - error
                    group_msg = None
                    for skey, svalue, compiled_val in compiled_schema:
                        if isinstance(skey, Inclusive) and skey.group_of_inclusion == group:
                            group_msg = skey.msg
                            break
                    msg = group_msg or ("some but not all values in the same group of inclusion '%s'" % group)
                    errors.append(er.InclusiveInvalid(
                        msg, path + [VirtualPathComponent(group)]
                    ))

            if errors:
                raise er.MultipleInvalid(errors)

            return output

        return validate_dict

    def _compile_list(self, schema):
        """Compile a list schema."""
        return self._compile_sequence(schema, list)

    def _compile_tuple(self, schema):
        """Compile a tuple schema."""
        return self._compile_sequence(schema, tuple)

    def _compile_sequence(self, schema, seq_type):
        """Compile a sequence schema."""
        if not schema:
            # Empty schema - accept any sequence
            def validate_empty_sequence(path, data):
                if not isinstance(data, (list, tuple)):
                    raise er.SequenceTypeInvalid('expected a list', path)
                return seq_type(data) if seq_type == list else data
            return validate_empty_sequence

        # Compile each schema element
        compiled_elements = []
        remove_elements = []
        for i, element in enumerate(schema):
            compiled = self._compile(element)
            if isinstance(element, Remove):
                remove_elements.append(compiled)
            else:
                compiled_elements.append(compiled)

        all_compiled_removes = [self._compile(e) for e in schema if isinstance(e, Remove)]
        all_compiled_non_remove = [(e, self._compile(e)) for e in schema if not isinstance(e, Remove)]

        def validate_sequence(path, data):
            if not isinstance(data, (list, tuple)):
                raise er.SequenceTypeInvalid('expected a list', path)

            output = []
            errors = []

            for i, item in enumerate(data):
                item_path = path + [i]

                # Check remove elements first
                removed = False
                for remove_compiled in all_compiled_removes:
                    try:
                        remove_compiled(item_path, item)
                        removed = True
                        break
                    except er.Invalid:
                        pass

                if removed:
                    continue

                # Try each non-remove schema element
                item_errors = []
                matched = False
                for schema_elem, elem_compiled in all_compiled_non_remove:
                    try:
                        new_val = elem_compiled(item_path, item)
                        output.append(new_val)
                        matched = True
                        break
                    except er.Invalid as e:
                        item_errors.append(e)

                if not matched:
                    if item_errors:
                        errors.extend(item_errors)
                    else:
                        errors.append(er.Invalid('no valid validators for item', item_path))

            if errors:
                raise er.MultipleInvalid(errors)

            if seq_type == tuple:
                # Check for namedtuple
                if hasattr(schema, '_fields'):
                    return type(schema)(*output)
                return tuple(output)
            return output

        return validate_sequence

    def _compile_set(self, schema):
        """Compile a set/frozenset schema."""
        schema_type = type(schema)
        compiled_elements = [self._compile(e) for e in schema]

        def validate_set(path, data):
            if not isinstance(data, (set, frozenset, list, tuple)):
                raise er.Invalid('expected a set', path)

            output = []
            errors = []

            for item in data:
                item_path = path + []
                matched = False
                for elem_compiled in compiled_elements:
                    try:
                        new_val = elem_compiled(item_path, item)
                        output.append(new_val)
                        matched = True
                        break
                    except er.Invalid:
                        pass

                if not matched:
                    errors.append(er.Invalid('invalid item', item_path))

            if errors:
                raise er.MultipleInvalid(errors)

            return schema_type(output)

        return validate_set

    def _compile_object(self, schema):
        """Compile an Object schema."""
        dict_compiled = self._compile_dict(schema)

        def validate_object(path, data):
            if schema.cls is not UNDEFINED:
                if not isinstance(data, schema.cls):
                    raise er.ObjectInvalid('expected %s' % schema.cls, path)

            # Get attributes as dict
            attrs = _iterate_object(data)
            attrs_dict = dict(attrs)

            validated = dict_compiled(path, attrs_dict)

            # Write back
            for key, value in validated.items():
                setattr(data, key, value)

            return data

        return validate_object

    def __call__(self, data):
        """Validate data against schema."""
        try:
            return self._compiled([], data)
        except er.MultipleInvalid:
            raise
        except er.Invalid as e:
            raise er.MultipleInvalid([e])

    def __eq__(self, other):
        if isinstance(other, Schema):
            return self.schema == other.schema
        return False

    def __str__(self):
        return str(self.schema)

    def __repr__(self):
        return '<Schema(%r) object at 0x%x>' % (self.schema, id(self))

    @classmethod
    def infer(cls, data, **kwargs):
        """Build a schema by inspecting the structure of data."""
        if isinstance(data, dict):
            schema = {Required(k): cls.infer(v) for k, v in data.items()}
        elif isinstance(data, list):
            if data:
                schema = [cls.infer(data[0])]
            else:
                schema = list
        else:
            schema = type(data)
        return cls(schema, **kwargs)

    def extend(self, schema, required=None, extra=None):
        """Extend this schema with additional keys."""
        if not isinstance(self.schema, dict):
            raise er.SchemaError('Cannot extend a non-dict schema')

        if isinstance(schema, Schema):
            if not isinstance(schema.schema, dict):
                raise er.SchemaError('Cannot extend with a non-dict schema')
            new_schema_dict = schema.schema
        elif isinstance(schema, dict):
            new_schema_dict = schema
        else:
            raise er.SchemaError('Cannot extend with a non-dict schema')

        # Build merged schema
        merged = {}

        # Get key identity (inner value for Markers)
        def key_id(k):
            if isinstance(k, Marker):
                return k.schema
            return k

        # Copy existing schema
        existing = {}
        for k, v in self.schema.items():
            existing[key_id(k)] = (k, v)

        # Start with existing
        for kid, (k, v) in existing.items():
            merged[k] = v

        # Merge new schema
        for nk, nv in new_schema_dict.items():
            nkid = key_id(nk)
            if nkid in existing:
                ok, ov = existing[nkid]
                if isinstance(ov, dict) and isinstance(nv, dict):
                    # Recursive merge
                    merged[ok] = Schema(ov).extend(nv).schema
                else:
                    merged[ok] = nv
            else:
                merged[nk] = nv

        new_required = required if required is not None else self.required
        new_extra = extra if extra is not None else self.extra

        return self.__class__(merged, required=new_required, extra=new_extra)


def _iterate_object(obj):
    """Iterate over an object's attributes."""
    seen = set()
    if hasattr(obj, '__slots__'):
        for slot in obj.__slots__:
            if slot not in seen:
                seen.add(slot)
                try:
                    yield slot, getattr(obj, slot)
                except AttributeError:
                    pass
    if hasattr(obj, '__dict__'):
        for key, value in obj.__dict__.items():
            if key not in seen:
                seen.add(key)
                yield key, value
