"""JMGL HTTP API.

Endpoints (see /docs for the OpenAPI UI):
  POST /v1/evaluate          evaluate one action            (client or admin key)
  POST /v1/evaluate/batch    evaluate up to N actions        (client or admin key)
  GET  /v1/laws[/{id}]       the laws in force               (public by default)
  GET  /v1/audit             paginated audit log             (admin key)
  DELETE /v1/audit/{id}      erase one audit record          (admin key; GDPR erasure)
  GET  /v1/auth/check        verify a key and see its role   (any valid key)
  GET  /healthz              liveness
  GET  /readyz               readiness (model + audit store)
  GET  /metrics              Prometheus metrics
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import Depends, FastAPI, HTTPException, Path, Query, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .. import engine as E
from .._version import __version__
from . import schemas as S
from .audit_store import AuditStore, input_digest, make_store, retention_cutoff
from .config import Settings, get_settings
from .logging_config import configure_logging
from .metrics import Metrics
from .ratelimit import Limiter, make_limiter
from .security import ANONYMOUS, Principal, optional_principal, require_admin, require_client
from .service import GovernanceService

log = logging.getLogger("jmgl.api")

Client = Annotated[Principal, Depends(require_client)]
Admin = Annotated[Principal, Depends(require_admin)]


# ---------------------------------------------------------------------------- middleware
class BodySizeLimit:
    """Reject bodies larger than max_bytes with 413 (checks Content-Length and streamed size)."""

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] in ("GET", "HEAD", "OPTIONS"):
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers") or [])
        cl = headers.get(b"content-length")
        if cl is not None and cl.isdigit() and int(cl) > self.max_bytes:
            return await self._reject(send)
        chunks: list[bytes] = []
        size = 0
        while True:
            msg = await receive()
            if msg["type"] == "http.disconnect":
                return
            body = msg.get("body", b"")
            size += len(body)
            if size > self.max_bytes:
                return await self._reject(send)
            chunks.append(body)
            if not msg.get("more_body"):
                break
        replayed = False

        async def replay() -> Message:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)

    async def _reject(self, send: Send) -> None:
        body = json.dumps({"detail": f"Request body exceeds {self.max_bytes} bytes"}).encode()
        await send({"type": "http.response.start", "status": 413,
                    "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})


SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
    "Cross-Origin-Resource-Policy": "same-site",
}


def client_ip(request: Request) -> str:
    if request.app.state.settings.trust_proxy_headers:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def enforce_rate_limit(request: Request, principal: Principal, cost: int = 1) -> None:
    st: Settings = request.app.state.settings
    if not st.rate_limit_enabled:
        return
    if principal.role == "anonymous":
        bucket, limit = f"ip:{client_ip(request)}", st.rate_limit_public_per_minute
    else:
        bucket, limit = f"key:{principal.key_id}", st.rate_limit_per_minute
    retry = request.app.state.limiter.hit(bucket, limit, cost)
    if retry is not None:
        request.app.state.metrics.rate_limited.inc()
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Rate limit exceeded",
                            headers={"Retry-After": str(retry), "X-RateLimit-Limit": str(limit)})


# ---------------------------------------------------------------------------- app factory
def create_app(settings: Optional[Settings] = None, *, service: Optional[GovernanceService] = None,
               store: Optional[AuditStore] = None, limiter: Optional[Limiter] = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_json)
    metrics = Metrics()
    service = service or GovernanceService(settings.mode, settings.laws_path)
    store = store or make_store(settings)
    limiter = limiter or make_limiter(settings.rate_limit_redis_url)

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        if settings.mode == "ensemble" and settings.warmup_model:
            await asyncio.to_thread(service.load_model)
        metrics.model_loaded.set(1 if service.model_loaded else 0)
        task = asyncio.create_task(_housekeeping(app))
        log.info("jmgl api started", extra={"event": "startup", "version": __version__,
                                             "mode": settings.mode, "model_loaded": service.model_loaded,
                                             "audit_backend": store.name, "region": settings.region,
                                             "auth_enabled": settings.auth_enabled})
        try:
            yield
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            store.close()

    async def _housekeeping(app: FastAPI) -> None:
        last_purge = 0.0
        while True:
            try:
                if settings.mode == "ensemble" and not service.model_loaded:
                    await asyncio.to_thread(service.maybe_retry_model)
                    metrics.model_loaded.set(1 if service.model_loaded else 0)
                cutoff = retention_cutoff(settings.audit_retention_days)
                if cutoff and time.monotonic() - last_purge >= settings.audit_purge_interval_minutes * 60:
                    n = await asyncio.to_thread(store.purge, cutoff)
                    last_purge = time.monotonic()
                    if n:
                        log.info("audit retention purge", extra={"event": "audit_purge", "deleted": n})
            except Exception:  # noqa: BLE001
                log.exception("housekeeping failed")
            await asyncio.sleep(30)

    app = FastAPI(
        title="Jackson Moral Governance Layer (JMGL) API",
        version=__version__,
        description=("Policy engine for AI workflows: evaluates a proposed action against the JMGL laws "
                     "and returns ALLOW, BLOCK, MODIFY, or ESCALATE. **Pilot-stage**: see the README "
                     "for published accuracy and limitations."),
        license_info={"name": "MIT", "url": "https://opensource.org/licenses/MIT"},
        lifespan=lifespan,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )
    app.state.settings = settings
    app.state.metrics = metrics
    app.state.service = service
    app.state.store = store
    app.state.limiter = limiter
    app.state.client_hashes = settings.client_key_set
    app.state.admin_hashes = settings.admin_key_set
    metrics.build.info({"version": __version__, "engine_version": E.ENGINE_VERSION, "region": settings.region})

    app.add_middleware(BodySizeLimit, max_bytes=settings.max_body_bytes)  # innermost

    @app.middleware("http")
    async def observe(request: Request, call_next):
        rid = request.headers.get("x-request-id", "")[:64] or uuid.uuid4().hex
        request.state.request_id = rid
        t0 = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception:
            log.exception("unhandled error", extra={"request_id": rid})
            response = JSONResponse({"detail": "Internal server error", "request_id": rid}, status_code=500)
        dt = time.perf_counter() - t0
        route = request.scope.get("route")
        route_path = getattr(route, "path", "unmatched")
        metrics.requests.labels(request.method, route_path, str(status_code)).inc()
        metrics.latency.labels(route_path).observe(dt)
        response.headers["X-Request-ID"] = rid
        for k, v in SECURITY_HEADERS.items():
            response.headers.setdefault(k, v)
        if route_path not in ("/healthz", "/readyz", "/metrics"):
            p = getattr(request.state, "principal", None)
            log.info("request", extra={"request_id": rid, "method": request.method, "path": route_path,
                                       "status": status_code, "duration_ms": round(dt * 1000, 2),
                                       "key_id": p.key_id if p else None, "client_ip": client_ip(request)})
        return response

    if settings.cors_origin_list:  # outermost, so even 413/500 carry CORS headers
        app.add_middleware(
            CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=False,
            allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
            allow_headers=["X-API-Key", "Authorization", "Content-Type", "X-Request-ID"],
            expose_headers=["X-Request-ID", "Retry-After", "X-RateLimit-Limit"], max_age=600)

    @app.exception_handler(HTTPException)
    async def http_exc(request: Request, exc: HTTPException):
        return JSONResponse({"detail": exc.detail, "request_id": getattr(request.state, "request_id", None)},
                            status_code=exc.status_code, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_exc(request: Request, exc: RequestValidationError):
        errs = [{"loc": e.get("loc"), "msg": e.get("msg"), "type": e.get("type")} for e in exc.errors()]
        return JSONResponse({"detail": errs, "request_id": getattr(request.state, "request_id", None)},
                            status_code=422)

    # ------------------------------------------------------------------ helpers
    def _validate(req: S.EvaluateRequest, idx: Optional[int] = None) -> None:
        where = f"items[{idx}]." if idx is not None else ""
        if len(req.action) > settings.max_action_chars:
            raise HTTPException(422, f"{where}action exceeds {settings.max_action_chars} characters")
        if not req.action.strip():
            raise HTTPException(422, f"{where}action must not be blank")
        if len(req.context.history) > settings.max_history_turns:
            raise HTTPException(422, f"{where}context.history exceeds {settings.max_history_turns} turns")
        if any(len(h) > settings.max_action_chars for h in req.context.history):
            raise HTTPException(422, f"{where}a history turn exceeds {settings.max_action_chars} characters")
        if req.mode and req.mode != settings.mode and not settings.allow_mode_override:
            raise HTTPException(422, "mode override is disabled on this server")

    def _evaluate_one(req: S.EvaluateRequest, principal: Principal) -> S.EvaluateResponse:
        t0 = time.perf_counter()
        r = service.evaluate(req.action, req.context.history, req.mode, req.include_signals)
        eval_s = r.pop("_eval_seconds")
        metrics.eval_latency.labels(r["engine"]["mode"]).observe(eval_s)
        metrics.decisions.labels(r["decision"], r["engine"]["mode"]).inc()
        if r["engine"]["degraded"]:
            metrics.degraded.inc()
        rec_id = str(uuid.uuid4())
        audited = False
        if store.name != "none":
            try:
                store.write({
                    "id": rec_id, "timestamp": datetime.now(timezone.utc),
                    "decision": r["decision"], "rule_id": r["rule_id"],
                    "laws_triggered": [law["id"] for law in r["laws_triggered"]],
                    "mode": r["engine"]["mode"], "degraded": r["engine"]["degraded"],
                    "confidence": r["confidence"],
                    "grace_force": r["grace_force"]["score"] if r["grace_force"] else None,
                    "input_sha256": input_digest(req.action, settings.audit_hash_secret),
                    "input_raw": req.action if settings.audit_log_raw else None,
                    "key_id": principal.key_id, "region": settings.region,
                    "engine_version": r["engine"]["engine_version"], "laws_sha256": service.laws_sha256,
                })
                audited = True
            except Exception:  # noqa: BLE001
                metrics.audit_errors.inc()
                log.exception("audit write failed")
                if settings.audit_required:
                    raise HTTPException(503, "Audit log unavailable; no verdict issued (JMGL_AUDIT_REQUIRED=true)") from None
        return S.EvaluateResponse(id=rec_id, latency_ms=round((time.perf_counter() - t0) * 1000, 2),
                                  audited=audited, **r)

    # ------------------------------------------------------------------ routes
    @app.get("/", include_in_schema=False)
    def root():
        return {"name": "JMGL API", "version": __version__, "docs": "/docs" if settings.docs_enabled else None,
                "health": "/healthz", "ready": "/readyz"}

    @app.get("/healthz", response_model=S.Health, tags=["ops"], summary="Liveness probe")
    def healthz():
        return {"status": "ok", "version": __version__}

    @app.get("/readyz", response_model=S.Ready, tags=["ops"], summary="Readiness probe",
             responses={503: {"model": S.Ready}})
    def readyz(response: Response):
        audit_ok = store.ping()
        want_model = settings.mode == "ensemble"
        if not audit_ok and settings.audit_required:
            state = "not_ready"
        elif want_model and not service.model_loaded:
            state = "not_ready" if settings.require_model else "degraded"
        else:
            state = "ready"
        if state == "not_ready":
            response.status_code = 503
        return {"status": state, "version": __version__, "engine_mode": settings.mode,
                "model_loaded": service.model_loaded, "model_error": service.model_error if want_model else None,
                "audit_backend": store.name, "audit_ok": audit_ok, "region": settings.region}

    @app.get("/metrics", tags=["ops"], summary="Prometheus metrics", response_class=Response)
    def metrics_endpoint(request: Request, principal: Principal = Depends(optional_principal)):
        if not settings.metrics_public and principal.role != "admin":
            raise HTTPException(401, "Admin API key required for /metrics")
        return Response(generate_latest(metrics.registry), media_type=CONTENT_TYPE_LATEST)

    @app.get("/v1/auth/check", tags=["auth"], summary="Verify an API key")
    def auth_check(principal: Client):
        return {"valid": True, "role": principal.role, "key_id": principal.key_id}

    @app.get("/v1/laws", response_model=S.LawsResponse, tags=["laws"], summary="List the laws in force")
    def laws(request: Request, principal: Principal = Depends(optional_principal)):
        if not settings.laws_public and principal.role == "anonymous":
            raise HTTPException(401, "Missing or invalid API key", headers={"WWW-Authenticate": "ApiKey"})
        enforce_rate_limit(request, principal)
        meta = service.laws_doc.get("meta", {})
        return {"spec_version": meta.get("spec_version"), "status": meta.get("status"),
                "laws_sha256": service.laws_sha256, "laws": list(service.laws.values())}

    @app.get("/v1/laws/{law_id}", response_model=S.Law, tags=["laws"], summary="Get one law")
    def law(request: Request, law_id: Annotated[str, Path(pattern=r"^JL-\d{2}$")],
            principal: Principal = Depends(optional_principal)):
        if not settings.laws_public and principal.role == "anonymous":
            raise HTTPException(401, "Missing or invalid API key", headers={"WWW-Authenticate": "ApiKey"})
        enforce_rate_limit(request, principal)
        if law_id not in service.laws:
            raise HTTPException(404, "Unknown law id")
        return service.laws[law_id]

    @app.post("/v1/evaluate", response_model=S.EvaluateResponse, tags=["evaluate"],
              summary="Evaluate one proposed action",
              responses={401: {"model": S.ErrorBody}, 413: {"model": S.ErrorBody},
                         422: {"model": S.ErrorBody}, 429: {"model": S.ErrorBody}, 503: {"model": S.ErrorBody}})
    def evaluate(request: Request, body: S.EvaluateRequest, principal: Client):
        enforce_rate_limit(request, principal)
        _validate(body)
        return _evaluate_one(body, principal)

    @app.post("/v1/evaluate/batch", response_model=S.BatchResponse, tags=["evaluate"],
              summary="Evaluate several actions (each counts toward the rate limit)")
    def evaluate_batch(request: Request, body: S.BatchRequest, principal: Client):
        if len(body.items) > settings.max_batch_items:
            raise HTTPException(422, f"items exceeds {settings.max_batch_items}")
        enforce_rate_limit(request, principal, cost=len(body.items))
        for i, item in enumerate(body.items):
            _validate(item, i)
        return {"results": [_evaluate_one(item, principal) for item in body.items]}

    @app.get("/v1/audit", response_model=S.AuditPage, tags=["audit"], summary="Browse the audit log (newest first)")
    def audit(request: Request, principal: Admin,
              limit: Annotated[int, Query(ge=1, le=200)] = 50,
              cursor: Annotated[Optional[str], Query(pattern=r"^\d{1,19}$")] = None,
              decision: Optional[S.Decision] = None,
              rule_id: Annotated[Optional[str], Query(pattern=r"^JL-(\d{2}|ML)$")] = None,
              since: Optional[datetime] = None, until: Optional[datetime] = None):
        enforce_rate_limit(request, principal)
        items, nxt = store.page(limit, int(cursor) if cursor else None, decision, rule_id, since, until)
        return {"items": items, "next_cursor": str(nxt) if nxt is not None else None, "backend": store.name}

    @app.delete("/v1/audit/{record_id}", status_code=204, tags=["audit"],
                summary="Erase one audit record (e.g. a data-subject erasure request)")
    def audit_delete(request: Request, principal: Admin,
                     record_id: Annotated[str, Path(pattern=r"^[0-9a-f-]{36}$")]):
        enforce_rate_limit(request, principal)
        if not store.delete(record_id):
            raise HTTPException(404, "Audit record not found")
        log.info("audit record erased", extra={"event": "audit_erase", "record_id": record_id,
                                               "key_id": principal.key_id})
        return Response(status_code=204)

    _ = ANONYMOUS  # re-exported for type checkers
    return app


def __getattr__(name: str):
    """`uvicorn jmgl.server.app:app` creates the app lazily from the environment."""
    if name == "app":
        globals()["app"] = create_app()
        return globals()["app"]
    raise AttributeError(name)
