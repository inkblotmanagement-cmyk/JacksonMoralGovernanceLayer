import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from jmgl.server.app import create_app  # noqa: E402
from jmgl.server.config import Settings  # noqa: E402
from jmgl.server.security import hash_key  # noqa: E402

CLIENT_KEY = "jmgl_test_client_key_0123456789abcdef"
ADMIN_KEY = "jmgl_test_admin_key_0123456789abcdef"


def make_settings(tmp_path, **over) -> Settings:
    base = dict(
        environment="test", mode="rules", warmup_model=False, log_json=True, log_level="WARNING",
        client_key_hashes=hash_key(CLIENT_KEY), admin_key_hashes=hash_key(ADMIN_KEY),
        audit_backend="sql", audit_database_url=f"sqlite:///{tmp_path}/audit.db",
        audit_file_path=tmp_path / "audit.jsonl", rate_limit_per_minute=1000,
        rate_limit_public_per_minute=1000, cors_origins="http://localhost:5173",
    )
    base.update(over)
    return Settings(_env_file=None, **base)


@pytest.fixture
def settings_factory(tmp_path):
    return lambda **over: make_settings(tmp_path, **over)


@pytest.fixture
def client_factory(tmp_path):
    clients = []

    def _make(**over):
        app = create_app(make_settings(tmp_path, **over))
        c = TestClient(app)
        c.__enter__()
        clients.append(c)
        return c

    yield _make
    for c in clients:
        c.__exit__(None, None, None)


@pytest.fixture
def client(client_factory):
    return client_factory()


@pytest.fixture
def ch():
    return {"X-API-Key": CLIENT_KEY}


@pytest.fixture
def ah():
    return {"X-API-Key": ADMIN_KEY}
