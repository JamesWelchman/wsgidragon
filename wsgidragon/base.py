import json as js
import signal
from collections import namedtuple
from enum import Enum
from sys import stderr
from functools import partial
from traceback import format_exc
from datetime import datetime
from random import randbytes
from time import time

from wsgidragoncall import InnerCaller

from .envvar import environ


WSGIHandler = namedtuple("WSGIHandler", (
    "environ",
    "start_response",
    "service_name",
    "handler",
))

Context = namedtuple("Context", (
    "trace_id",
    "parent_id",
    "span_id",
))

Request = namedtuple("Request", (
    "method",
    "path",
    "params",
    "headers",
    "content_type",
    "body",
))

# Logging
class InnerLogger:
    def __init__(self, service_name):
        self.service_name = service_name
        self._ctx = None
        self._client = None

    def set_ctx(self, ctx):
        self._ctx = ctx

    def unset_ctx(self):
        self._ctx = None

    def set_client(self, client):
        self._client = client

    def unset_client(self):
        self._client = None

    def log(self, level, msg, tags):
        msg = {
            "service": self.service_name,
            "ts": datetime.utcnow().isoformat(),
            "level": level,
            "msg": msg,
        }
        if self._ctx:
            msg['trace_id'] = self._ctx.trace_id
            msg['span_id'] = self._ctx.span_id
            if self._ctx.parent_id:
                msg['parent_id'] = self._ctx.parent_id

        if self._client:
            msg['client'] = self._client

        msg.update(tags)
        print(js.dumps(msg, separators=(",", ":")))


class Logger:
    @staticmethod
    def info(msg, *args, tags=None):
        global INNER_LOGGER
        tags = tags or {}

        INNER_LOGGER.log("INFO", msg.format(*args), tags)

    @staticmethod
    def error(msg, *args, tags=None):
        global INNER_LOGGER
        tags = tags or {}

        INNER_LOGGER.log("ERROR", msg.format(*args), tags)

    @staticmethod
    def exception(msg, *args, tags=None):
        global INNER_LOGGER

        tags = tags or {}
        tags['exc'] = format_exc()

        INNER_LOGGER.log("ERROR", msg.format(*args), tags)


# This variable gets set
# in the make_application
# function below.
INNER_LOGGER = None
logger = Logger

def self_eval(e):
    return e


class CallFuture:
    def __init__(self, ref, log_tags, on_complete=None):
        self._ref = ref
        self._call_recv = None
        self._on_complete = on_complete or self_eval
        self._val = None
        self._log_tags = log_tags

    def _set_call_recv(self, call_recv):
        global logger

        self._call_recv = call_recv
        tags = {**self._log_tags, **call_recv.log_tags()}
        logger.info("call complete", tags=tags)

        val = call_recv.get()
        try:
            if isinstance(Exception, val):
                complete_val = val
            else:
                complete_val = self._on_complete(val)
        except Exception:
            self._val = val
        else:
            self._val = complete_val

    def is_ready(self):
        global INNER_CALLER

        if self._call_recv:
            return True

        call_recv = INNER_CALLER.poll_ready(self._ref)
        if call_recv:
            self._set_call_recv(call_recv)
            return True

        return False

    def wait(self):
        global INNER_CALLER

        if self._call_recv:
            return self._val

        INNER_CALLER.block_on_ids([self._ref])
        call_recv = INNER_CALLER.poll_ready(self._ref)
        if call_recv:
            self._set_call_recv(call_recv)
            return self._val

        raise RuntimeError("didn't block waiting for call")

    def wait_or_raise(self):
        val = self.wait()
        if isinstance(Exception, val):
            raise val

        return val


class Caller:
    @staticmethod
    def call(method,
             host,
             port=80,
             path_segms=None,
             use_ssl=False,
             params=None,
             headers=None,
             body=None,
             timeout=10):
        global INNER_CALLER

        body = body or b""
        path_segms = path_segms or [""]

        log_tags = {
            "url.host": host,
            "url.port": port,
            "url.path": "/".join(path_segms),
            "http.req_content_length": len(body),
            "http.ssl": use_ssl,
        }

        return CallFuture(INNER_CALLER.call(method,
                                            host,
                                            port,
                                            path_segms,
                                            use_ssl,
                                            params or [],
                                            headers or [],
                                            body,
                                            timeout * 1000), log_tags)

    @staticmethod
    def call_json(self, method, path, json, headers=None, params=None):
        json = js.dumps(json)
        headers = headers or []
        headers.append(
            ("Content-Type", "application/json"),
        )

        ref = INNER_CALLER.call(method, path, headers, params or [], json)
        return CallFuture(ref)


# Our inner caller
INNER_CALLER = None
caller = Caller

class StatusCode(Enum):
    OK = (200, "Ok")
    BAD_REQUEST = (400, "Bad Request")
    NOT_FOUND = (404, "Not Found")
    INTERNAL_SERVER_ERROR = (500, "Internal Server Error")
    GATEWAY_TIMEOUT = (504, "Gateway Timeout")


class Response:
    def __init__(self, ctx):
        self._ctx = ctx
        self.clear()

    def clear(self):
        self._log_tags = {}
        self._headers = [
            ("X-TraceId", self._ctx.trace_id),
        ]
        self._status = None
        self._payload = (b"",)

    def set_status(self, status):
        self._status = status

    def resp_head(self, status, headers):
        self._headers.extend(headers)
        self.set_status(status)

    def status_code(self):
        return self._status

    def add_header(self, key, value):
        self._headers.append(
            (key, value)
        )

    def status_str(self):
        return get_status_str(self._status)

    def headers(self):
        return self._headers + [("Content-Length", str(len(self._payload[0])))]

    def add_log_tag(self, key, val):
        self._log_tags[key] = val

    def log_tags(self):
        tags = self._log_tags.copy()
        if self._status:
            tags['http.status'] = self._status.value[0]

        return tags

    def set_body(self, content_type, body):
        self._headers.append(
            ("Content-Type", content_type)
        )
        self._payload = (body,)

    def payload(self):
        return self._payload

    def set_not_found(self):
        self._status = StatusCode.NOT_FOUND

    def set_bad_request(self, reason):
        self.clear()
        self._headers.append(
            ("Error", reason),
        )
        self.set_status(StatusCode.BAD_REQUEST)

    def set_internal_server_error(self, reason):
        self.clear()
        self._headers.append(
            ("Error", reason)
        )
        self.set_status(StatusCode.INTERNAL_SERVER_ERROR)

    def set_timeout(self):
        self.clear()
        self._headers.append(
            ("Error", "application timeout"),
        )
        self.set_status(StatusCode.GATEWAY_TIMEOUT)

    def set_json(self, json):
        json = bytes(js.dumps(json, separators=(',', ':')), encoding='utf8')
        self._headers.append(
            ("Content-Type", "application/json")
        )
        self._payload = (json,)

    def set_html(self, html):
        html = bytes(html, encoding='utf8')
        self.set_body("text/html; charset=UTF-8", html)
        self.set_status(StatusCode.OK)


def application_with_request(wsgi_handler, resp):
    # Build the request tuple
    req = Request(
        wsgi_handler.environ['REQUEST_METHOD'],
        wsgi_handler.environ['PATH_INFO'],
        wsgi_handler.environ['QUERY_STRING'],
        get_headers(wsgi_handler.environ),
        # Set content-type if we have it
        wsgi_handler.environ.get('CONTENT_TYPE'),
        wsgi_handler.environ['wsgi.input'],
    )

    wsgi_handler.handler(req, resp)


class TimeoutError(BaseException):
    pass


def application_with_timeout(wsgi_handler, resp):
    global logger

    # Is there an X-Timeout header in the request?
    timeout_str = wsgi_handler.environ.get('HTTP_X_TIMEOUT')
    now = int(time())
    timeout = None

    if timeout_str:
        try:
            timeout = int(timeout_str)
        except ValueError:
            logger.warn("invalid X-Timeout header")
            timeout = None

    if not timeout:
        try:
            timeout = now + int(environ['WSGI_DRAGON_GATEWAY_TIMEOUT'])
        except ValueError:
            logger.warn("couldn't parse timeout as int")
            timeout = now + 10
    else:
        # Check this timeout is actually in the future
        # and we have at least five seconds for the request
        if timeout < now + 5:
            resp.set_bad_request("timeout is in the past")
            return

    try:
        active = True
        def sighandler(_sig_num, _frame):
            if active:
                raise TimeoutError

        signal.signal(signal.SIGALRM, sighandler)
        signal.alarm(timeout - now)
        application_with_request(wsgi_handler, resp)
    except TimeoutError:
        resp.set_timeout()
    finally:
        active = False


def application_with_response(wsgi_handler, ctx, req_info):
    resp = Response(ctx)

    try:
        application_with_timeout(wsgi_handler, resp)

        # Okay write the response
        wsgi_handler.start_response(resp.status_str(), resp.headers())
        logger.info("request complete", tags={
            **req_info,
            **resp.log_tags(),
        })
        return resp.payload()

    except Exception as exc:
        # Send back internal server error
        wsgi_handler.start_response("500 Internal Server Error", [
            ("X-TraceId", ctx.trace_id),
            ("Error", str(exc)),
        ])
        logger.exception("application crashed", tags={
            **req_info,
            "error": str(exc),
            "http.status": 500,
        })
        return (b"",)


def application_with_req_info(wsgi_handler, ctx):
    global INNER_LOGGER

    req_info = {
        'http.method': wsgi_handler.environ['REQUEST_METHOD'],
        'url.path': wsgi_handler.environ['PATH_INFO'],
        'url.port': int(wsgi_handler.environ['SERVER_PORT']),
        'url.host': wsgi_handler.environ['SERVER_NAME'],
    }

    if "CONTENT_TYPE" in wsgi_handler.environ:
        req_info['http.content_type'] = wsgi_handler.environ['CONTENT_TYPE']

    if "CONTENT_LENGTH" in wsgi_handler.environ:
        req_info['http.req_content_length'] = wsgi_handler.environ['CONTENT_LENGTH']

    client = None
    if 'HTTP_X_CLIENT' in wsgi_handler.environ:
        client = wsgi_handler.environ['HTTP_X_CLIENT']
    elif 'HTTP_USER_AGENT' in wsgi_handler.environ:
        client = wsgi_handler.environ['HTTP_USER_AGENT']

    if client:
        INNER_LOGGER.set_client(client)

    return application_with_response(wsgi_handler, ctx, req_info)


def application_with_ctx(wsgi_handler):
    global INNER_LOGGER, INNER_CALLER

    traceparent = wsgi_handler.environ.get("HTTP_TRACEPARENT")
    (trace_id, parent_id) = (None, None)

    if traceparent:
        try:
            (trace_id, parent_id) = parse_traceparent(traceparent)
        except ValueError as exc:
            logger.warn("invalid traceparent header", {
                "error": str(exc),
            })
            (trace_id, parent_id) = (None, None)

    if not trace_id:
        trace_id = randbytes(16).hex()

    ctx = Context(
        trace_id,
        parent_id,
        # span_id
        randbytes(8).hex(),
    )

    INNER_LOGGER.set_ctx(ctx)
    INNER_CALLER.set_trace(ctx.trace_id, ctx.span_id)

    return application_with_req_info(wsgi_handler, ctx)


def application_with_logger(wsgi_handler):
    global INNER_LOGGER, logger

    try:
        INNER_LOGGER.unset_ctx()
        INNER_LOGGER.unset_client()
        return application_with_ctx(wsgi_handler)
    except Exception as exc:
        logger.exception("application crashed")

        # try and send back internal server error
        wsgi_handler.start_response("500 Internal Server Error", [
            ("Error", str(exc)),
        ])
        return (b"",)

def application(wsgi_handler):
    global INNER_CALLER

    try:
        # Clear out INNER_CALLER for
        # a new request
        INNER_CALLER.clear()

        return application_with_logger(wsgi_handler)
    except Exception as exc:
        esend = wsgi_handler.environ['wsgi.errors']
        esend("application crashed")
        esend(format_exc())

        # try and send back internal server error
        wsgi_handler.start_response("500 Internal Server Error", [
            ("Error", str(exc)),
        ])
        return (b"",)
        


def make_application(name, handler):
    # Create the Logger
    global INNER_LOGGER, INNER_CALLER

    INNER_LOGGER = InnerLogger(name)
    INNER_CALLER = InnerCaller(name)

    def app(environ, start_response):
        wsgi_handler = WSGIHandler(environ, start_response, name, handler)
        return application(wsgi_handler)

    return app


def get_status_str(status):
    """
    get_status_str will return a string
    for our status (e.g 200 OK)
    """
    return f"{status.value[0]} {status.value[1]}"


def get_headers(environ):
    headers = []
    for k, v in environ.items():
        if k.startswith("HTTP_"):
            headers.append((k[5:], v))

    return headers


def parse_traceparent(traceparent):
    if len(traceparent) != 55:
        raise ValueError("traceparent header not of length 55")

    parts = traceparent.split('-')
    if len(parts) != 4:
        raise ValueError("expected 4 parts in traceparent header")

    if parts[0] != "00":
        raise ValueError(f"unsupported traceparent version {parts[0]}")

    trace_id = parts[1].lower()
    if len(trace_id) != 32 or not is_hexstring(trace_id):
        raise ValueError("invalid trace_id")

    parent_id = parts[2].lower()
    if len(parent_id) != 16 or not is_hexstring(parent_id):
        raise ValueError("invalid parent_id")

    if len(parts[3]) != 2:
        raise ValueError("invalid flags")

    return (trace_id, parent_id)


def is_hexstring(s):
    if len(s) % 2 != 0:
        return False

    for c in s:
        if c not in "0123456789abcdef":
            return False

    return True
