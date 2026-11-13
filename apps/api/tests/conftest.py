import os
import re
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any

import httpx
import pytest
import redis
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from sqlalchemy import create_engine, text

from operon.core.config import Settings
from operon.core.email import MemoryEmailSender
from operon.main import create_app

API_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TEST_DB_APP_URL = os.environ.get(
    "OPERON_TEST_DATABASE_URL",
    "postgresql+asyncpg://operon_app:operon_app_dev@localhost:5432/operon_test",
)
TEST_DB_OWNER_URL = os.environ.get(
    "OPERON_TEST_MIGRATIONS_DATABASE_URL",
    "postgresql+psycopg://operon_owner:operon_owner_dev@localhost:5432/operon_test",
)
TEST_REDIS_URL = os.environ.get("OPERON_TEST_REDIS_URL", "redis://localhost:6379/15")
PASSWORD = "correct horse battery staple"


def alembic_config() -> Config:
    cfg = Config(os.path.join(API_ROOT, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(API_ROOT, "migrations"))
    cfg.attributes["database_url"] = TEST_DB_OWNER_URL
    return cfg


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> None:
    cfg = alembic_config()
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")


@pytest.fixture(scope="session")
def owner_engine() -> Any:
    engine = create_engine(TEST_DB_OWNER_URL)
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def clean_state(owner_engine: Any) -> None:
    """Every test starts from empty tables (catalogue kept) and an empty Redis database."""
    with owner_engine.begin() as conn:
        tables = (
            conn.execute(
                text(
                    "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
                    "AND tablename NOT IN ('alembic_version', 'permissions')"
                )
            )
            .scalars()
            .all()
        )
        if tables:
            conn.execute(text(f"TRUNCATE {', '.join(tables)} CASCADE"))
    redis.Redis.from_url(TEST_REDIS_URL).flushdb()


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "environment": "test",
        "database_url": TEST_DB_APP_URL,
        "migrations_database_url": TEST_DB_OWNER_URL,
        "redis_url": TEST_REDIS_URL,
        "log_json": True,
        "health_check_timeout_seconds": 1.0,
        "email_backend": "memory",
        # Fast hashing in tests; production parameters are covered by config defaults.
        "password_hash_time_cost": 1,
        "password_hash_memory_kib": 1024,
        "password_hash_parallelism": 1,
        # Protocol test servers live on non-public test hostnames.
        "allow_private_integration_hosts": True,
        "workflow_backend": "inline",
        # Tests drive escalation directly; no background loop.
        "inline_maintenance_interval_seconds": 0,
    }
    values.update(overrides)
    return Settings.model_validate(values)


class Api:
    """Test client that behaves like the web app: keeps cookies, echoes the CSRF token."""

    def __init__(self, client: httpx.AsyncClient, app: FastAPI) -> None:
        self.http = client
        self.app = app
        self.org_id: str | None = None

    @property
    def outbox(self) -> list[Any]:
        mailer: MemoryEmailSender = self.app.state.mailer
        return mailer.outbox

    def last_link_token(self, to: str, path: str) -> str:
        for message in reversed(self.outbox):
            if message.to.lower() == to.lower():
                match = re.search(rf"{re.escape(path)}\?token=([\w-]+)", message.text)
                if match:
                    return match.group(1)
        raise AssertionError(f"No {path} link emailed to {to}")

    def _headers(self, extra: dict[str, str] | None) -> dict[str, str]:
        headers = dict(extra or {})
        csrf = self.http.cookies.get("operon_csrf")
        if csrf:
            headers.setdefault("X-CSRF-Token", csrf)
        if self.org_id:
            headers.setdefault("X-Operon-Organisation", self.org_id)
        return headers

    async def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        if "operon_csrf" not in self.http.cookies:
            await self.http.get("/api/v1/health/live")
        headers = self._headers(kwargs.pop("headers", None))
        return await self.http.request(method, f"/api/v1{path}", headers=headers, **kwargs)

    async def get(self, path: str, **kw: Any) -> httpx.Response:
        return await self.request("GET", path, **kw)

    async def post(self, path: str, **kw: Any) -> httpx.Response:
        return await self.request("POST", path, **kw)

    async def put(self, path: str, **kw: Any) -> httpx.Response:
        return await self.request("PUT", path, **kw)

    async def patch(self, path: str, **kw: Any) -> httpx.Response:
        return await self.request("PATCH", path, **kw)

    async def delete(self, path: str, **kw: Any) -> httpx.Response:
        return await self.request("DELETE", path, **kw)

    async def sign_up(
        self,
        email: str,
        org: str = "Acme Distribution",
        name: str = "Test User",
        password: str = PASSWORD,
    ) -> str:
        """Register, verify via the emailed link, sign in, select the new organisation."""
        r = await self.post(
            "/auth/register",
            json={
                "email": email,
                "password": password,
                "full_name": name,
                "organisation_name": org,
            },
        )
        assert r.status_code == 202, r.text
        token = self.last_link_token(email, "/verify-email")
        assert (await self.post("/auth/verify-email", json={"token": token})).status_code == 200
        await self.login(email, password)
        orgs = (await self.get("/organisations")).json()
        self.org_id = orgs[0]["id"]
        return self.org_id

    async def login(self, email: str, password: str = PASSWORD) -> httpx.Response:
        r = await self.post("/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200, r.text
        return r


AppFactory = Callable[..., AbstractAsyncContextManager[Api]]


@asynccontextmanager
async def _api_for(app: FastAPI) -> AsyncIterator[Api]:
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(
            app=app, raise_app_exceptions=False, client=("203.0.113.10", 50000)
        )
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield Api(client, app)


@pytest.fixture
def api_factory() -> AppFactory:
    def factory(
        app: FastAPI | None = None, **overrides: object
    ) -> AbstractAsyncContextManager[Api]:
        return _api_for(app or create_app(make_settings(**overrides)))

    return factory


@pytest.fixture
async def api(api_factory: AppFactory) -> AsyncIterator[Api]:
    async with api_factory() as a:
        yield a


@pytest.fixture
async def second_api(api: Api) -> AsyncIterator[Api]:
    """Another browser against the same app (separate cookie jar, shared outbox)."""
    transport = httpx.ASGITransport(
        app=api.app, raise_app_exceptions=False, client=("203.0.113.20", 50000)
    )
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield Api(client, api.app)


# Back-compat for Phase 0 tests.
ClientFactory = Callable[..., AbstractAsyncContextManager[httpx.AsyncClient]]


@asynccontextmanager
async def _client_for(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


@pytest.fixture
def client_factory() -> ClientFactory:
    def factory(
        app: FastAPI | None = None, **overrides: object
    ) -> AbstractAsyncContextManager[httpx.AsyncClient]:
        return _client_for(app or create_app(make_settings(**overrides)))

    return factory


@pytest.fixture
async def client(client_factory: ClientFactory) -> AsyncIterator[httpx.AsyncClient]:
    async with client_factory() as c:
        yield c


# --- integrations: protocol test servers -------------------------------------------------------


class Fakes:
    def __init__(self) -> None:
        from tests.fakes.odoo import FakeOdoo
        from tests.fakes.shopify import FakeShopify

        self.odoo = FakeOdoo()
        self.shopify = FakeShopify()

    def route(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "odoo.test":
            return self.odoo.handler(request)
        if request.url.host.endswith(".myshopify.com"):
            return self.shopify.handler(request)
        return httpx.Response(599, text="no route in tests")


@pytest.fixture
def fakes() -> Fakes:
    return Fakes()


@pytest.fixture
async def iapi(api_factory: AppFactory, fakes: Fakes) -> AsyncIterator[Api]:
    """API whose connectors talk to the protocol test servers."""
    app = create_app(make_settings())
    app.state.http_factory = lambda: httpx.AsyncClient(transport=httpx.MockTransport(fakes.route))
    async with api_factory(app) as a:
        yield a
