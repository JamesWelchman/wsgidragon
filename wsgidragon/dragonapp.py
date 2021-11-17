from .routes import (
    make_application,
    add_route,
)
from .api import JsonApi, BadCode, Api
from .base import (
    logger,
    StatusCode,
)
from .paramschema import ParamError
from .jsonschema import ValidationError


class DragonApp:
    def __init__(self, name):
        self._app = make_application(name)
        self.name = name

    def __call__(self, environ, start_response):
        return self._app(environ, start_response)

    def add(self,
            handler,
            methods=None,
            path=None,
            param_schema=None,
            request_schema=None,
            response_schema=None,
            status_codes=None,
            api=None):

        api = api or Api
        assert methods, "empty methods not allowed"
        assert isinstance(path, tuple), "path must be a tuple or namedtuple"
        assert issubclass(api, Api), "api must be Api subclass"
        status_codes = status_codes or [StatusCode.OK]

        api = api(self.name, methods, path, param_schema, request_schema, response_schema, status_codes)
        add_route(methods, path, api, handler)

    def add_json(self, handler, methods=None, path=None, request_schema=None, response_schema=None, param_schema=None, status_codes=None):
        self.add(handler, methods, path, param_schema, request_schema, response_schema, status_codes, JsonApi)
