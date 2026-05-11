from voluptuous import Invalid, MultipleInvalid
from voluptuous.schema_builder import Schema, VirtualPathComponent


def humanize_error(data, validation_error, max_sub_error_length=500):
    """Return a human-readable string for a validation error."""
    if isinstance(validation_error, MultipleInvalid):
        errors = validation_error.errors
    else:
        errors = [validation_error]

    lines = []
    for error in errors:
        error_str = str(error)

        # Try to extract the offending value
        try:
            value = data
            for path_component in error.path:
                if isinstance(path_component, VirtualPathComponent):
                    raise KeyError('virtual path component')
                if isinstance(value, (list, tuple)):
                    value = value[path_component]
                else:
                    value = value[path_component]

            value_repr = repr(value)
            if len(value_repr) > max_sub_error_length:
                value_repr = value_repr[:max_sub_error_length] + '...'

            lines.append('%s. Got %s' % (error_str, value_repr))
        except (KeyError, IndexError, TypeError):
            lines.append(error_str)

    return '\n'.join(lines)


def validate_with_humanized_errors(data, schema, max_sub_error_length=500):
    """Validate data and raise humanized errors."""
    try:
        return schema(data)
    except Invalid as e:
        raise Invalid(humanize_error(data, e, max_sub_error_length=max_sub_error_length))
