
from mako.template import Template

from pathlib import Path
from urllib.parse import parse_qs

from .base import StatusCode, logger
from .envvar import environ

TEMPLATE_DIR = Path(__file__).parent.absolute() / "templates"

INDEX = Template(open(TEMPLATE_DIR / "index.mako").read())
CSS = open(TEMPLATE_DIR / "style.css", 'rb').read()
MAIN = Template(open(TEMPLATE_DIR / "main.mako").read())
ROUTE = Template(open(TEMPLATE_DIR / "route.mako").read())


class BadRequest(Exception):
    pass


def doc_handler(request, response, routes):
    # we assume path starts with /doc
    if not request.path.startswith("/doc"):
        raise RuntimeError("not a documentation path")

    # strip /doc from the front
    path = request.path[4:]
    doc_creator = {
        "": get_index,
        "/index.html": get_index,
        "/main.html": get_main,
        "/style.css": get_style,
        "/route": get_route,
    }.get(path)

    if not doc_creator:
        response.set_not_found()
        return

    try:
        response.set_body(*doc_creator(request, routes))
    except BadRequest as exc:
        response.set_bad_request(str(exc))
    except Exception as exc:
        logger.exception("couldn't create template", tags={
            "error": str(exc),
            "function": doc_creator.__name__,
        })
        response.set_internal_server_error(str(exc))
    else:
        response.set_status(StatusCode.OK)


def get_index(request, routes):
    return "text/html; encoding=UTF-8", bytes(INDEX.render(routes=routes), encoding='utf8')


def get_style(_request, _routes):
    return "text/css", CSS


def get_main(_request, _routes):
    return "text/html; encoding=UTF-8", bytes(MAIN.render(environ=environ), encoding='utf8')


def get_route(request, routes):
    qs = parse_qs(request.params)
    if "route" not in qs or len(qs['route']) != 1:
        raise BadRequest("invalid route")

    route_id = qs['route'][0]

    for r in routes:
        print(r.api.id, r.api.name)
        if r.api.id == route_id:
            route = r
            break
    else:
        raise BadRequest("couldn't find route")

    return "text/html; encoding=UTF-8", bytes(ROUTE.render(route=route), encoding='utf8')
