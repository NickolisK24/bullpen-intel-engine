from dataclasses import dataclass

from flask import jsonify


@dataclass(frozen=True)
class QueryParamError:
    parameter: str
    message: str

    def to_payload(self):
        return {
            'status': 'error',
            'reason_code': 'invalid_query_parameter',
            'parameter': self.parameter,
            'message': self.message,
        }


def query_param_error_response(error: QueryParamError):
    return jsonify(error.to_payload()), 400


def parse_int_param(
    args,
    name,
    *,
    default=None,
    minimum=None,
    maximum=None,
    clamp_max=False,
    required=False,
):
    raw = args.get(name)
    if raw in (None, ''):
        if required:
            return None, QueryParamError(name, f'{name} is required.')
        return default, None

    try:
        value = int(str(raw), 10)
    except (TypeError, ValueError):
        return None, QueryParamError(name, f'{name} must be an integer.')

    if minimum is not None and value < minimum:
        return None, QueryParamError(name, f'{name} must be at least {minimum}.')

    if maximum is not None and value > maximum:
        if clamp_max:
            return maximum, None
        return None, QueryParamError(name, f'{name} must be no greater than {maximum}.')

    return value, None


def parse_positive_int_param(args, name, *, default=None, maximum=None, clamp_max=True):
    return parse_int_param(
        args,
        name,
        default=default,
        minimum=1,
        maximum=maximum,
        clamp_max=clamp_max,
    )


def parse_non_negative_int_param(args, name, *, default=None, maximum=None, clamp_max=False):
    return parse_int_param(
        args,
        name,
        default=default,
        minimum=0,
        maximum=maximum,
        clamp_max=clamp_max,
    )


def parse_enum_param(args, name, allowed_values, *, default=None, normalize=str.upper):
    raw = args.get(name)
    if raw in (None, ''):
        return default, None

    value = str(raw).strip()
    normalized = normalize(value) if normalize else value
    allowed = set(allowed_values)
    if normalized not in allowed:
        allowed_display = ', '.join(sorted(str(item) for item in allowed))
        return None, QueryParamError(
            name,
            f'{name} must be one of: {allowed_display}.',
        )
    return normalized, None
