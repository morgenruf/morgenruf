"""Flask API initialization, consistent errors, and browser session protection."""

from __future__ import annotations

import hmac
import secrets

from flask import jsonify, request, session
from flask_smorest import Api

from src.core.api_schemas import Error


def _validation_details(messages):
    """Turn webargs locations and nested Marshmallow errors into form paths."""
    details: dict[str, list[str]] = {}
    locations = {"json", "query", "querystring", "path", "form", "headers", "cookies", "files", "json_or_form"}

    def collect(value, path=""):
        if isinstance(value, dict):
            for key, nested in value.items():
                # Schema-level errors describe this object, rather than a
                # field literally named `_schema`.
                child_path = path if key == "_schema" else ".".join(filter(None, (path, str(key))))
                collect(nested, child_path)
            return
        errors = value if isinstance(value, list) else [value]
        details.setdefault(path or "root.server", []).extend(str(error) for error in errors)

    if isinstance(messages, dict):
        for key, value in messages.items():
            collect(value, "" if key in locations or key == "_schema" else str(key))
    else:
        collect(messages)
    return details


class BrowserApi(Api):
    ERROR_SCHEMA = Error

    def handle_http_exception(self, error):
        data = getattr(error, "data", None) or {}
        body = {"error": data.get("message") or error.description}
        messages = data.get("messages") or data.get("errors")
        if messages:
            # The error message remains compatible with existing callers;
            # structured field validation is additive.
            body["details"] = _validation_details(messages)
        return jsonify(body), error.code or 500


def init_api(app):
    api = app.extensions.get("morgenruf_api")
    if api is not None:
        return api
    app.config.setdefault("API_TITLE", "Morgenruf browser API")
    app.config.setdefault("API_VERSION", "1")
    app.config.setdefault("OPENAPI_VERSION", "3.0.3")
    app.config.setdefault("OPENAPI_URL_PREFIX", "/")
    app.config.setdefault("OPENAPI_JSON_PATH", "openapi.json")
    api = BrowserApi(app)

    # apispec's default nullable reference is a union with an unrestricted
    # object. That widens generated clients to `object | NextChat` and loses
    # the response contract. An allOf wrapper keeps a nullable named model.
    def nullable_reference(converter, field, *, ret):
        choices = ret.get("anyOf", [])
        references = [item for item in choices if "$ref" in item]
        if field.allow_none and len(choices) == 2 and len(references) == 1:
            ret.pop("anyOf")
            return {"allOf": references, "nullable": True}
        return {}

    api.ma_plugin.converter.add_attribute_function(nullable_reference)
    api.spec.components.security_scheme(
        "sessionCookie", {"type": "apiKey", "in": "cookie", "name": app.config.get("SESSION_COOKIE_NAME", "session")}
    )
    api.spec.components.security_scheme("csrfHeader", {"type": "apiKey", "in": "header", "name": "X-CSRF-Token"})
    app.extensions["morgenruf_api"] = api
    return api


def register_api_blueprint(app, blueprint):
    init_api(app).register_blueprint(blueprint)


def api_errors(blueprint, *, conflict=None):
    """Document the consistent authentication, validation and service errors."""

    def decorate(view):
        for status in (400, 401, 403, 404, 409, 500, 503):
            schema = conflict if status == 409 and conflict is not None else Error
            view = blueprint.alt_response(status, schema=schema)(view)
        return view

    return decorate


def csrf_token():
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def install_browser_security(app):
    @app.before_request
    def protect_browser_mutations():
        if not request.path.startswith("/dashboard/api/") or request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
            return None
        # Authentication keeps its existing 401 precedence over CSRF errors.
        if not session.get("team_id"):
            return None
        expected = session.get("csrf_token", "")
        supplied = request.headers.get("X-CSRF-Token", "")
        if not expected or not hmac.compare_digest(expected, supplied):
            return jsonify(error="Invalid or missing CSRF token"), 403
        return None

    @app.after_request
    def private_browser_responses(response):
        if request.path.startswith(("/dashboard", "/api/public/", "/email/", "/oauth/", "/connect/zoom/")):
            response.headers["Cache-Control"] = "no-store"
        return response
