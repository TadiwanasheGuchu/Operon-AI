import httpx
from fastapi import FastAPI

from operon.core.errors import ApiError
from operon.main import create_app
from tests.conftest import ClientFactory, make_settings


async def test_request_id_is_generated(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/v1/health/live")
    assert len(resp.headers["x-request-id"]) == 32


async def test_valid_upstream_request_id_is_propagated(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/v1/health/live", headers={"x-request-id": "edge-1234abcd"})
    assert resp.headers["x-request-id"] == "edge-1234abcd"


async def test_malformed_request_id_is_replaced(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/v1/health/live", headers={"x-request-id": "bad id\r\n<script>"})
    assert resp.headers["x-request-id"] != "bad id\r\n<script>"
    assert len(resp.headers["x-request-id"]) == 32


async def test_not_found_uses_error_envelope(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/v1/does-not-exist")
    assert resp.status_code == 404
    error = resp.json()["error"]
    assert error["code"] == "not_found"
    assert error["request_id"] == resp.headers["x-request-id"]


def _app_with_failing_routes() -> FastAPI:
    app = create_app(make_settings())

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("secret connection string postgres://user:pw@host")

    @app.get("/expected")
    async def expected() -> None:
        raise ApiError(409, "conflict", "Already exists.", {"field": "name"})

    @app.get("/typed")
    async def typed(limit: int) -> int:
        return limit

    return app


async def test_unhandled_errors_never_leak_internals(client_factory: ClientFactory) -> None:
    async with client_factory(_app_with_failing_routes()) as client:
        resp = await client.get("/boom")
    assert resp.status_code == 500
    assert resp.json()["error"]["code"] == "internal_error"
    assert "secret" not in resp.text
    assert "postgres" not in resp.text


async def test_api_errors_are_client_visible(client_factory: ClientFactory) -> None:
    async with client_factory(_app_with_failing_routes()) as client:
        resp = await client.get("/expected")
    assert resp.status_code == 409
    assert resp.json()["error"]["details"] == {"field": "name"}


async def test_validation_errors_are_structured(client_factory: ClientFactory) -> None:
    async with client_factory(_app_with_failing_routes()) as client:
        resp = await client.get("/typed", params={"limit": "many"})
    assert resp.status_code == 422
    error = resp.json()["error"]
    assert error["code"] == "validation_error"
    assert error["details"]["errors"][0]["loc"] == ["query", "limit"]


async def test_openapi_schema_is_versioned(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/v1/openapi.json")
    assert resp.status_code == 200
    assert "/api/v1/health/ready" in resp.json()["paths"]


PROD_KEYS = "v1:cHJvZHVjdGlvbi10ZXN0LWtleS0zMi1ieXRlcy0hISE="


def test_docs_disabled_in_production() -> None:
    app = create_app(
        make_settings(
            environment="production",
            allow_private_integration_hosts=False,
            secret_keys=PROD_KEYS,
            email_backend="smtp",
            workflow_backend="temporal",
        )
    )
    assert app.docs_url is None


def test_production_refuses_unsafe_configuration() -> None:
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="OPERON_SECRET_KEYS"):
        make_settings(
            environment="production", allow_private_integration_hosts=False, email_backend="smtp"
        )
    with pytest.raises(ValidationError, match="Secure"):
        make_settings(
            environment="production",
            allow_private_integration_hosts=False,
            secret_keys=PROD_KEYS,
            email_backend="smtp",
            cookie_secure=False,
        )
    with pytest.raises(ValidationError, match="WORKFLOW_BACKEND"):
        make_settings(
            environment="production",
            allow_private_integration_hosts=False,
            secret_keys=PROD_KEYS,
            email_backend="smtp",
        )
    with pytest.raises(ValidationError, match="EMAIL_BACKEND"):
        make_settings(
            environment="production",
            allow_private_integration_hosts=False,
            secret_keys=PROD_KEYS,
            workflow_backend="temporal",
        )
