from urllib.parse import parse_qs


class ParamError(Exception):
    pass


class Param:
    def __init__(self, required=False, allow_duplicates=False):
        self.key = ""
        self.required = required
        self.allow_duplicates = allow_duplicates
        self.ignore = False

    def __call__(self, required=False, allow_duplicates=False, key=None, ignore=False):
        self.required = required
        self.allow_duplicates = allow_duplicates
        self.key = key or ""
        self.ignore = ignore
        return self

    def validate(self, val, on_err):
        pass

class SessionId(Param):
    def validate(self, val, on_err):
        if len(vals) != 1:
            on_err("session_id must be unique")
            return

        session_id = vals[0].lower()
        if len(vals[0]) != 32 or not is_hexstring(vals[0]):
            on_err("session_id is a hexstring of length 32")
            return

        return session_id


class ParamSchemaMeta(type):
    def __new__(cls, name, bases, attrs):
        return super().__new__(cls, name, bases, attrs)


class ParamSchema(metaclass=ParamSchemaMeta):
    def __init__(self, qs):
        self.qs = qs

    def __iter__(self):
        pass


class SessionIdSchema(ParamSchema):
    session_id = SessionId(required=True, allow_duplicates=False)


def on_err_with_key(key, on_err_clb):
    def on_err(reason):
        return on_err_clb(key, reason)

    return on_err


def build(qs, schema, on_err):
    qs = parse_qs(qs)
    schema = schema(qs)
    ans = {}

    for (key, validator) in schema:
        vals = qs.get(key, [])
        if not vals and validator.required:
            raise ParamError(f"missing required key {key}")

        if not vals:
            continue

        if len(vals) != 1 and not validator.allow_duplicates:
            raise ParamError(f"duplicate {key} not allowed")

        new_vals = []
        err_handler = on_err_with_key(key, on_err)
        for v in vals:
            v = validator.validate(v, err_handler)
            if v is not None:
                
                new_vals.append(v)

            if v is None and not validator.ignore:
                raise ParamError(f"not ignoring invalid param for {key}")

        ans[key] = new_vals

    return ans

