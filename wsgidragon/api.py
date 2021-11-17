import json as js
from urllib.parse import parse_qs
from hashlib import md5

from .base import logger
from .jsonschema import validate


class BadCode(Exception):
    pass


class Api:
    def __init__(self, service_name, methods, path, param_schema, request_schema, response_schema, status_codes):
        self.service_name = service_name
        self.methods = methods
        self.path = path
        self.param_schema = param_schema
        self.request_schema = request_schema
        self.response_schema = response_schema
        self.status_codes = status_codes
        id_b = bytes("".join(path) + "".join(methods), encoding='utf8')
        self._id = md5(id_b).digest().hex()[:10]

    def build_params(self, raw_query):
        return parse_qs(raw_query)

    def build_req_body(self, _content_type, reader):
        return reader.read()

    def build_response(self, body):
        """
        """
        return "", body

    def validate_status_code(self, code):
        if code not in self.status_codes:
            raise BadCode

    def schema(self, path):
        """
        schema must return a dictionary - it should schema
        information about this endpoint.
        """
        return {}

    def schema_html(self, path):
        """
        schema_html must return inner html
        for the documentation engine. It must
        return a string.
        """

        return "<p>schema</p>"

    @property
    def name(self):
        if type(self.path) is tuple:
            return "/".join(self.path)

        # path is a namedtuple - use the names instead
        return "/".join(self.path._fields)

    @property
    def id(self):
        return self._id


class JsonApi(Api):
    def build_req_body(self, content_type, reader):
        # Won't read if schema not set
        if self.request_schema is None:
            return b""

        if content_type.lower() != "application/json":
            raise TypeError("expected json request body")

        # Okay - read it
        body = js.load(reader)

        # validate it
        validate(body, self.request_schema)

        # okay return it
        return body

    def build_response(self, body):
        if body is None and self.response_schema is None:
            return b""

        if body is None and self.response_schema:
            raise RuntimeError("body is empty, but schema is not")

        if body and self.response_schema is None:
            raise RuntimeError("body is populated, but not schema set")

        # We must have a body and a schema
        # validate it
        validate(body, self.response_schema)

        body = bytes(js.dumps(body, separators=(",", ":")), encoding='utf8')
        return "application/json", body
    
