"""JMGL HTTP API (FastAPI). Install with `pip install "jmgl[server]"` and run `jmgl-server serve`.

`create_app()` builds the ASGI app; `app` is a lazily created module-level instance for
`uvicorn jmgl.server.app:app`.
"""
from __future__ import annotations

__all__ = ["create_app"]


def create_app(*args, **kwargs):  # pragma: no cover - thin re-export
    from .app import create_app as _create_app
    return _create_app(*args, **kwargs)
