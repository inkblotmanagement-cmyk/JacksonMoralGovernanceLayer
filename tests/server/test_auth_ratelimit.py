"""Authentication (hashed keys, roles), rate limiting, and production config guards."""
import pytest
from pydantic import ValidationError

from jmgl.server.config import Settings
from jmgl.server.ratelimit import MemoryLimiter, RedisLimiter
from jmgl.server.security import generate_key, hash_key

from .conftest import ADMIN_KEY, CLIENT_KEY

BODY = {"action": "How do I turn on two-factor authentication on my own account?"}


def test_missing_and_invalid_key(client):
    r = client.post("/v1/evaluate", json=BODY)
    assert r.status_code == 401 and r.headers["WWW-Authenticate"] == "ApiKey"
    assert client.post("/v1/evaluate", json=BODY, headers={"X-API-Key": "nope"}).status_code == 401
    assert client.post("/v1/evaluate", json=BODY, headers={"X-API-Key": "x" * 600}).status_code == 401
    assert 'jmgl_auth_failures_total{reason="invalid"} 3.0' in client.get("/metrics").text


def test_client_admin_and_bearer(client):
    assert client.post("/v1/evaluate", json=BODY, headers={"X-API-Key": CLIENT_KEY}).status_code == 200
    assert client.post("/v1/evaluate", json=BODY, headers={"X-API-Key": ADMIN_KEY}).status_code == 200
    assert client.post("/v1/evaluate", json=BODY,
                       headers={"Authorization": f"Bearer {CLIENT_KEY}"}).status_code == 200
    assert client.get("/v1/auth/check", headers={"X-API-Key": CLIENT_KEY}).json()["role"] == "client"
    assert client.get("/v1/auth/check", headers={"X-API-Key": ADMIN_KEY}).json()["role"] == "admin"


def test_audit_requires_admin(client):
    assert client.get("/v1/audit").status_code == 401
    assert client.get("/v1/audit", headers={"X-API-Key": CLIENT_KEY}).status_code == 403
    assert client.get("/v1/audit", headers={"X-API-Key": ADMIN_KEY}).status_code == 200


def test_key_hash_never_plaintext(settings_factory):
    key, h = generate_key()
    assert key.startswith("jmgl_") and h == hash_key(key) and key not in h
    with pytest.raises(ValidationError):
        settings_factory(client_key_hashes="not-a-hash")
    st = settings_factory(client_key_hashes=f"sha256:{h.upper()}, {hash_key('other')}")
    assert h in st.client_key_set and len(st.client_key_set) == 2


def test_auth_disabled_dev_only(client_factory):
    c = client_factory(auth_enabled=False)
    assert c.post("/v1/evaluate", json=BODY).status_code == 200


@pytest.mark.parametrize("over,msg", [
    ({"auth_enabled": False}, "AUTH_ENABLED"),
    ({"client_key_hashes": "", "admin_key_hashes": ""}, "KEY_HASHES"),
    ({"client_key_hashes": hash_key("jmgl_dev_client_DO_NOT_USE_IN_PRODUCTION")}, "sample keys"),
    ({"cors_origins": "*"}, "CORS"),
])
def test_production_guards(settings_factory, over, msg):
    with pytest.raises(ValidationError, match=msg):
        settings_factory(environment="production", **over)
    assert settings_factory(environment="production").environment == "production"


def test_rate_limit_per_key(client_factory):
    c = client_factory(rate_limit_per_minute=3)
    h = {"X-API-Key": CLIENT_KEY}
    codes = [c.post("/v1/evaluate", json=BODY, headers=h).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]
    r = c.post("/v1/evaluate", json=BODY, headers=h)
    assert int(r.headers["Retry-After"]) >= 1 and r.headers["X-RateLimit-Limit"] == "3"
    # a different key has its own bucket
    assert c.post("/v1/evaluate", json=BODY, headers={"X-API-Key": ADMIN_KEY}).status_code == 200
    assert "jmgl_rate_limited_total 2.0" in c.get("/metrics").text


def test_rate_limit_batch_cost(client_factory):
    c = client_factory(rate_limit_per_minute=5)
    h = {"X-API-Key": CLIENT_KEY}
    assert c.post("/v1/evaluate/batch", json={"items": [BODY] * 4}, headers=h).status_code == 200
    assert c.post("/v1/evaluate/batch", json={"items": [BODY] * 2}, headers=h).status_code == 429
    assert c.post("/v1/evaluate", json=BODY, headers=h).status_code == 200


def test_rate_limit_public_by_ip(client_factory):
    c = client_factory(rate_limit_public_per_minute=2)
    assert [c.get("/v1/laws").status_code for _ in range(3)] == [200, 200, 429]


def test_rate_limit_disabled(client_factory):
    c = client_factory(rate_limit_enabled=False, rate_limit_per_minute=1)
    h = {"X-API-Key": CLIENT_KEY}
    assert all(c.post("/v1/evaluate", json=BODY, headers=h).status_code == 200 for _ in range(3))


def test_memory_limiter_window():
    lim = MemoryLimiter()
    assert lim.hit("b", 2) is None and lim.hit("b", 2) is None
    assert lim.hit("b", 2) >= 1
    assert lim.hit("b", 2, cost=0) is None
    lim.reset()
    assert lim.hit("b", 2, cost=2) is None


def test_redis_limiter_shared():
    fakeredis = pytest.importorskip("fakeredis")
    server = fakeredis.FakeServer()
    a = RedisLimiter(client=fakeredis.FakeRedis(server=server))
    b = RedisLimiter(client=fakeredis.FakeRedis(server=server))  # second "replica"
    assert a.hit("k", 3) is None and b.hit("k", 3) is None and a.hit("k", 3) is None
    assert b.hit("k", 3) >= 1


def test_redis_limiter_fails_open():
    class Down:
        def pipeline(self):
            raise ConnectionError("redis down")
    assert RedisLimiter(client=Down()).hit("k", 1) is None


def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("JMGL_MODE", "rules")
    monkeypatch.setenv("JMGL_RATE_LIMIT_PER_MINUTE", "7")
    monkeypatch.setenv("JMGL_CORS_ORIGINS", "https://a.example, https://b.example")
    st = Settings(_env_file=None)
    assert st.mode == "rules" and st.rate_limit_per_minute == 7
    assert st.cors_origin_list == ["https://a.example", "https://b.example"]
