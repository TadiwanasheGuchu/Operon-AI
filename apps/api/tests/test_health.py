import httpx

from tests.conftest import ClientFactory


async def test_liveness(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/v1/health/live")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "service": "operon-api", "version": "0.1.0"}


async def test_readiness_reports_database_and_redis(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/v1/health/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert {c["name"]: c["status"] for c in body["checks"]} == {"database": "ok", "redis": "ok"}


async def test_readiness_fails_closed_without_leaking_details(
    client_factory: ClientFactory,
) -> None:
    async with client_factory(redis_url="redis://localhost:6390/0") as client:
        resp = await client.get("/api/v1/health/ready")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "unavailable"
    checks = {c["name"]: c for c in body["checks"]}
    assert checks["redis"] == {"name": "redis", "status": "unavailable", "latency_ms": None}
    assert checks["database"]["status"] == "ok"
    assert "6390" not in resp.text
    assert "Connection" not in resp.text


async def test_readiness_reports_database_outage(client_factory: ClientFactory) -> None:
    async with client_factory(
        database_url="postgresql+asyncpg://operon_app:wrong@localhost:5432/operon_test"
    ) as client:
        resp = await client.get("/api/v1/health/ready")
    assert resp.status_code == 503
    assert {c["name"]: c["status"] for c in resp.json()["checks"]}["database"] == "unavailable"
    assert "password" not in resp.text.lower()
