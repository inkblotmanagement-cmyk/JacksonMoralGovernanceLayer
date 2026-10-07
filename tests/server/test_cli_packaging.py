"""CLI helpers and data-file resolution for installed packages."""
import json

from jmgl import _resources
from jmgl.server import cli
from jmgl.server.security import hash_key


def test_gen_and_hash_key(capsys):
    assert cli.main(["gen-key"]) == 0
    out = capsys.readouterr().out
    key = out.split("store in a secret manager): ")[1].split()[0]
    h = out.strip().split(": ")[-1]
    assert hash_key(key) == h
    assert cli.main(["hash-key", key]) == 0
    assert capsys.readouterr().out.strip() == h


def test_check_config_redacts(capsys, monkeypatch):
    monkeypatch.setenv("JMGL_CLIENT_KEY_HASHES", "a" * 64)
    monkeypatch.setenv("JMGL_AUDIT_HASH_SECRET", "s3cret")
    assert cli.main(["check-config"]) == 0
    out = capsys.readouterr().out
    d = json.loads(out)
    assert d["client_key_hashes"] == "<set>" and "s3cret" not in out


def test_purge_cli(capsys, monkeypatch, tmp_path):
    monkeypatch.setenv("JMGL_AUDIT_DATABASE_URL", f"sqlite:///{tmp_path}/a.db")
    monkeypatch.setenv("JMGL_AUDIT_RETENTION_DAYS", "30")
    assert cli.main(["purge-audit"]) == 0
    assert "deleted 0" in capsys.readouterr().out


def test_resource_overrides(monkeypatch, tmp_path):
    assert _resources.laws_path().name == "laws.json" and _resources.laws_path().exists()
    assert (_resources.model_dir() / "clf.npz").exists()
    monkeypatch.setenv("JMGL_LAWS_PATH", str(tmp_path / "custom.json"))
    monkeypatch.setenv("JMGL_MODEL_DIR", str(tmp_path))
    assert _resources.laws_path() == tmp_path / "custom.json"
    assert _resources.model_dir() == tmp_path
