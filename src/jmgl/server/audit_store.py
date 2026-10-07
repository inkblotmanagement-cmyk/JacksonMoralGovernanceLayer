"""Audit log storage: SQL (SQLAlchemy; SQLite by default, PostgreSQL in production), an
append-only JSONL file, or none.

By default only a hash of the input is stored (HMAC-SHA256 when JMGL_AUDIT_HASH_SECRET is set,
which resists dictionary attacks on short inputs). Raw text is stored only when
JMGL_AUDIT_LOG_RAW=true; treat it as personal data (see docs/DATA_PROTECTION.md).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional, Protocol

FIELDS = ("seq", "id", "timestamp", "decision", "rule_id", "laws_triggered", "mode", "degraded",
          "confidence", "grace_force", "input_sha256", "input_raw", "key_id", "region",
          "engine_version", "laws_sha256")


def input_digest(text: str, secret: str = "") -> str:
    data = text.encode("utf-8")
    if secret:
        return hmac.new(secret.encode("utf-8"), data, hashlib.sha256).hexdigest()
    return hashlib.sha256(data).hexdigest()


class AuditStore(Protocol):
    name: str

    def write(self, rec: dict[str, Any]) -> None: ...
    def page(self, limit: int, cursor: Optional[int] = None, decision: Optional[str] = None,
             rule_id: Optional[str] = None, since: Optional[datetime] = None,
             until: Optional[datetime] = None) -> tuple[list[dict], Optional[int]]: ...
    def delete(self, record_id: str) -> bool: ...
    def purge(self, older_than: datetime) -> int: ...
    def ping(self) -> bool: ...
    def close(self) -> None: ...


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class NullStore:
    name = "none"

    def write(self, rec): return None
    def page(self, limit, cursor=None, decision=None, rule_id=None, since=None, until=None): return [], None
    def delete(self, record_id): return False
    def purge(self, older_than): return 0
    def ping(self): return True
    def close(self): return None


class FileStore:
    """Append-only JSONL. Fine for a single instance; use SQL for multiple replicas."""
    name = "file"

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._seq = 0
        if self.path.exists():
            for line in self.path.open(encoding="utf-8"):
                if line.strip():
                    self._seq = max(self._seq, int(json.loads(line).get("seq", 0)))

    def write(self, rec):
        with self._lock:
            self._seq += 1
            row = dict(rec, seq=self._seq)
            row["timestamp"] = _aware(row["timestamp"]).isoformat()
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, sort_keys=True) + "\n")
                fh.flush()
                os.fsync(fh.fileno())

    def _rows(self) -> list[dict]:
        if not self.path.exists():
            return []
        rows = []
        for line in self.path.open(encoding="utf-8"):
            if line.strip():
                r = json.loads(line)
                r["timestamp"] = datetime.fromisoformat(r["timestamp"])
                rows.append(r)
        return rows

    def page(self, limit, cursor=None, decision=None, rule_id=None, since=None, until=None):
        with self._lock:
            rows = self._rows()
        out = []
        for r in reversed(rows):
            if cursor is not None and r["seq"] >= cursor:
                continue
            if decision and r["decision"] != decision:
                continue
            if rule_id and r["rule_id"] != rule_id:
                continue
            if since and r["timestamp"] < _aware(since):
                continue
            if until and r["timestamp"] >= _aware(until):
                continue
            out.append(r)
            if len(out) > limit:
                break
        nxt = out[limit - 1]["seq"] if len(out) > limit else None
        return out[:limit], nxt

    def _rewrite(self, keep) -> int:
        with self._lock:
            rows = self._rows()
            kept = [r for r in rows if keep(r)]
            tmp = self.path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as fh:
                for r in kept:
                    fh.write(json.dumps(dict(r, timestamp=r["timestamp"].isoformat()), sort_keys=True) + "\n")
            os.replace(tmp, self.path)
            return len(rows) - len(kept)

    def delete(self, record_id):
        return self._rewrite(lambda r: r["id"] != record_id) > 0

    def purge(self, older_than):
        return self._rewrite(lambda r: r["timestamp"] >= _aware(older_than))

    def ping(self):
        return os.access(self.path.parent, os.W_OK)

    def close(self):
        return None


def normalize_db_url(url: str) -> str:
    """Accept Heroku/Render-style postgres:// URLs and select the psycopg (v3) driver."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


class SqlStore:
    name = "sql"

    def __init__(self, url: str, auto_create: bool = True) -> None:
        url = normalize_db_url(url)
        from sqlalchemy import (BigInteger, Boolean, Column, DateTime, Float, Integer, MetaData, String,
                                Table, Text, create_engine)
        from sqlalchemy.types import TypeDecorator

        class UTCDateTime(TypeDecorator):  # SQLite drops tzinfo; normalise to aware UTC
            impl = DateTime(timezone=True)
            cache_ok = True

            def process_bind_param(self, value, dialect):
                return _aware(value).astimezone(timezone.utc) if value is not None else None

            def process_result_value(self, value, dialect):
                return _aware(value) if value is not None else None

        if url.startswith("sqlite:///"):
            db_file = url.removeprefix("sqlite:///")
            if db_file and db_file != ":memory:":
                Path(db_file).parent.mkdir(parents=True, exist_ok=True)
        kwargs: dict[str, Any] = {"pool_pre_ping": True, "future": True}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}
            if ":memory:" in url or url in ("sqlite://", "sqlite:///"):
                from sqlalchemy.pool import StaticPool
                kwargs["poolclass"] = StaticPool
        elif url.startswith("postgresql"):
            kwargs["connect_args"] = {"connect_timeout": 5}
            kwargs.update(pool_size=5, max_overflow=5, pool_recycle=1800)
        self.engine = create_engine(url, **kwargs)
        self.md = MetaData()
        self.t = Table(
            "jmgl_audit", self.md,
            Column("seq", BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True),
            Column("id", String(36), nullable=False, unique=True),
            Column("timestamp", UTCDateTime(), nullable=False, index=True),
            Column("decision", String(16), nullable=False, index=True),
            Column("rule_id", String(16), nullable=False, index=True),
            Column("laws_triggered", String(200), nullable=False, default=""),
            Column("mode", String(16), nullable=False),
            Column("degraded", Boolean, nullable=False, default=False),
            Column("confidence", Float, nullable=True),
            Column("grace_force", Float, nullable=True),
            Column("input_sha256", String(64), nullable=False),
            Column("input_raw", Text, nullable=True),
            Column("key_id", String(32), nullable=False),
            Column("region", String(64), nullable=False),
            Column("engine_version", String(64), nullable=False),
            Column("laws_sha256", String(64), nullable=False),
        )
        self._auto_create = auto_create
        self._schema_ready = not auto_create
        self._schema_lock = threading.Lock()
        self._ensure_schema(raise_errors=False)  # DB may not be up yet; retried on use

    def _ensure_schema(self, raise_errors: bool = True) -> None:
        if self._schema_ready:
            return
        with self._schema_lock:
            if self._schema_ready:
                return
            try:
                self.md.create_all(self.engine)
                self._schema_ready = True
            except Exception as exc:
                logging.getLogger("jmgl.audit").warning(
                    "audit database not reachable yet", extra={"event": "audit_db_unavailable",
                                                              "error": f"{type(exc).__name__}"})
                if raise_errors:
                    raise

    def write(self, rec):
        self._ensure_schema()
        row = dict(rec)
        row["laws_triggered"] = ",".join(row.get("laws_triggered") or [])
        row.pop("seq", None)
        with self.engine.begin() as conn:
            conn.execute(self.t.insert().values(**row))

    def page(self, limit, cursor=None, decision=None, rule_id=None, since=None, until=None):
        from sqlalchemy import select
        self._ensure_schema()
        t = self.t
        q = select(t).order_by(t.c.seq.desc()).limit(limit + 1)
        if cursor is not None:
            q = q.where(t.c.seq < cursor)
        if decision:
            q = q.where(t.c.decision == decision)
        if rule_id:
            q = q.where(t.c.rule_id == rule_id)
        if since:
            q = q.where(t.c.timestamp >= _aware(since))
        if until:
            q = q.where(t.c.timestamp < _aware(until))
        with self.engine.connect() as conn:
            rows = [dict(r._mapping) for r in conn.execute(q)]
        for r in rows:
            r["laws_triggered"] = [x for x in (r["laws_triggered"] or "").split(",") if x]
        nxt = rows[limit - 1]["seq"] if len(rows) > limit else None
        return rows[:limit], nxt

    def delete(self, record_id):
        self._ensure_schema()
        with self.engine.begin() as conn:
            return conn.execute(self.t.delete().where(self.t.c.id == record_id)).rowcount > 0

    def purge(self, older_than):
        self._ensure_schema()
        with self.engine.begin() as conn:
            return int(conn.execute(self.t.delete().where(self.t.c.timestamp < _aware(older_than))).rowcount or 0)

    def ping(self):
        from sqlalchemy import text
        try:
            self._ensure_schema()
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    def close(self):
        self.engine.dispose()


def make_store(settings) -> AuditStore:
    if settings.audit_backend == "none":
        return NullStore()
    if settings.audit_backend == "file":
        return FileStore(settings.audit_file_path)
    return SqlStore(settings.audit_database_url, auto_create=settings.audit_auto_create)


def retention_cutoff(days: int) -> Optional[datetime]:
    return datetime.now(timezone.utc) - timedelta(days=days) if days > 0 else None
