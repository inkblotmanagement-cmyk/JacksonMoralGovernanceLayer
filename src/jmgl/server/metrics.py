"""Prometheus metrics (one registry per app instance, so tests stay isolated).

Run one uvicorn worker per container and scale with replicas/HPA; prometheus_client's
default registry is per process.
"""
from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, Info


class Metrics:
    def __init__(self) -> None:
        self.registry = CollectorRegistry()
        r = self.registry
        self.requests = Counter("jmgl_http_requests_total", "HTTP requests", ["method", "route", "status"], registry=r)
        self.latency = Histogram("jmgl_http_request_duration_seconds", "HTTP request latency", ["route"],
                                 buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5), registry=r)
        self.decisions = Counter("jmgl_decisions_total", "Evaluation decisions", ["decision", "mode"], registry=r)
        self.eval_latency = Histogram("jmgl_evaluation_duration_seconds", "Engine evaluation latency", ["mode"],
                                      buckets=(0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 1), registry=r)
        self.degraded = Counter("jmgl_degraded_evaluations_total",
                                "Evaluations served rules-only because the classifier was unavailable", registry=r)
        self.model_loaded = Gauge("jmgl_model_loaded", "1 if the learned classifier is loaded", registry=r)
        self.rate_limited = Counter("jmgl_rate_limited_total", "Requests rejected by the rate limiter", registry=r)
        self.auth_failures = Counter("jmgl_auth_failures_total", "Rejected authentication attempts", ["reason"],
                                     registry=r)
        self.audit_errors = Counter("jmgl_audit_write_errors_total", "Audit records that failed to persist",
                                    registry=r)
        self.build = Info("jmgl_build", "JMGL build information", registry=r)
