from collections import namedtuple

from .base import (
    make_application as base_make_application,
    StatusCode,
    logger,
)
from .api import Api, BadCode
from .dochandler import doc_handler
from .jsonschema import ValidationError


DragonRequest = namedtuple("DragonRequest", (
    "path",
    "params",
    "headers",
    "body",
))

Route = namedtuple("Route", (
    "methods",
    "path",
    "api",
    "clb",
))

ROUTES = []

def add_route(methods, path, api, clb):
    global ROUTES
    if methods and "OPTIONS" in methods:
        raise RuntimeError("can't register OPTIONS method")


    ROUTES.append(Route(methods, path, api, clb))


def route_handler(request, response):
    global ROUTES

    if request.path.startswith("/doc") and request.method == "GET":
        # return the documentation
        doc_handler(request, response, ROUTES)
        return

    for (methods, path, api, clb) in ROUTES:
        path = build_path(path, request.path.split('/')[1:])
        if path:
            # Log the path components
            for n, p in enumerate(path):
                response.add_log_tag(f"url.path.{n}", p)

            if request.method == "OPTIONS":
                schema_handler(path, response, api)
            elif request.method in methods:
                clb_handler(path, request, response, api, clb)
            else:
                response.set_not_found()

            # break due to path matched
            break
    else:
        response.set_not_found()


def make_application(name):
    return base_make_application(name, route_handler)


def build_path(path, path_parts):
    if len(path) != len(path_parts):
        return

    for (a, b) in zip(path, path_parts):
        if not check_regex(a, b):
            return

    # Okay - we need to build the path
    if type(path) is tuple:
        return tuple(path_parts)

    # It's a namedtuple
    return path.__class__(*path_parts)
        

def check_regex(a, b):
    return a == b


def schema_handler(path, response, api):
    response.set_json(api.schema(path))


def clb_handler(path, request, response, api, clb):
    try:
        params = api.build_params(request.params)
    except ParamError as exc:
        response.set_bad_request("invalid params - " + str(exc))
        return

    # We want to add the params to our logging
    for (key, vals) in params.items():
        if len(vals) == 1:
            response.add_log_tag(f"url.{key}", vals[0])
        elif len(vals) > 1:
            for n, v in enumerate(vals):
                if isinstance(v, (int, float, str, bool, type(None))):
                     response.add_log_tag(f"url.{key}.{n}", v)
                else:
                    try:
                        v = str(v)
                        response.add_log_tag(f"url.{key}.{n}", v)
                    except Exception:
                        # If we really can't log this value
                        pass

    try:
        body = api.build_req_body(request.content_type, request.body)
    except Exception as exc:
        response.set_bad_request("invalid body - " + str(exc))
        return

    req = DragonRequest(path, params, request.headers, body)

    try:
        resp_body = clb(req, response.resp_head)
    except Exception as exc:
        logger.exception("handler crashed")
        response.set_internal_server_error("handler crashed - " + str(exc))
        return

    # Is the response status code valid?
    try:
        if response.status_code() is None:
            response.set_status(StatusCode.OK)

        api.validate_status_code(response.status_code())
    except BadCode:
        logger.error("invalid status code from handler")
        response.set_internal_server_error("unregistered status code")
        return

    # Sanity check the response
    try:
        content_type, resp_body = api.build_response(resp_body)
    except ValidationError as exc:
        logger.error("invalid response body", tags={
            "error": str(exc),
        })
        response.set_internal_server_error("invalid response body - " + str(exc))
        return

    response.set_body(content_type, resp_body)
        
