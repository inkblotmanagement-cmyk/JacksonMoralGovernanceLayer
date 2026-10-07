"""`jmgl-server` command: serve, gen-key, hash-key, purge-audit, check-config."""
from __future__ import annotations

import argparse
import getpass
import json
import os
import sys


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="jmgl-server", description="JMGL HTTP API server and admin tools")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", help="run the API with uvicorn")
    s.add_argument("--host", default=os.environ.get("JMGL_HOST", "0.0.0.0"))  # noqa: S104 - container default
    s.add_argument("--port", type=int, default=int(os.environ.get("PORT", os.environ.get("JMGL_PORT", "8000"))))
    s.add_argument("--workers", type=int, default=int(os.environ.get("JMGL_WORKERS", "1")),
                   help="keep 1 per container and scale replicas (Prometheus metrics are per process)")
    sub.add_parser("gen-key", help="generate a new API key and print it with its SHA-256 hash")
    hk = sub.add_parser("hash-key", help="print the SHA-256 hash of an existing key (reads stdin if no arg)")
    hk.add_argument("key", nargs="?")
    sub.add_parser("purge-audit", help="delete audit records older than JMGL_AUDIT_RETENTION_DAYS")
    sub.add_parser("check-config", help="validate configuration from the environment and print it (no secrets)")
    a = p.parse_args(argv)

    if a.cmd == "gen-key":
        from .security import generate_key
        key, h = generate_key()
        print(f"API key (show once, store in a secret manager): {key}")
        print(f"SHA-256 hash (put this in JMGL_CLIENT_KEY_HASHES or JMGL_ADMIN_KEY_HASHES): {h}")
        return 0
    if a.cmd == "hash-key":
        from .security import hash_key
        key = a.key or (sys.stdin.readline().strip() if not sys.stdin.isatty() else getpass.getpass("API key: "))
        print(hash_key(key))
        return 0
    if a.cmd == "check-config":
        from .config import Settings
        st = Settings()
        d = st.model_dump(mode="json")
        for k in ("client_key_hashes", "admin_key_hashes", "audit_hash_secret", "audit_database_url",
                  "rate_limit_redis_url"):
            if d.get(k):
                d[k] = "<set>"
        print(json.dumps(d, indent=2))
        return 0
    if a.cmd == "purge-audit":
        from .audit_store import make_store, retention_cutoff
        from .config import Settings
        st = Settings()
        cutoff = retention_cutoff(st.audit_retention_days)
        if not cutoff:
            print("JMGL_AUDIT_RETENTION_DAYS=0: retention disabled, nothing purged")
            return 0
        n = make_store(st).purge(cutoff)
        print(f"deleted {n} audit records older than {cutoff.isoformat()}")
        return 0
    if a.cmd == "serve":
        import uvicorn
        uvicorn.run("jmgl.server.app:app", host=a.host, port=a.port, workers=a.workers,
                    proxy_headers=True, forwarded_allow_ips=os.environ.get("FORWARDED_ALLOW_IPS", "127.0.0.1"),
                    log_config=None, access_log=False, timeout_graceful_shutdown=20)
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
