"""Engine wrapper used by the API: mode selection, law mapping, graceful degradation.

The engine API (jmgl.evaluate_action / jmgl.evaluate_action_ensemble -> Verdict) is used
unchanged. If the learned classifier cannot load, the service serves rules-only verdicts,
flags them `engine.degraded = true`, and reports the cause on /readyz.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from pathlib import Path
from typing import Any, Optional

from .. import engine as E
from .._version import __version__

log = logging.getLogger("jmgl.service")

# classifier category -> the law it corresponds to (for laws_triggered when rule_id == JL-ML)
CATEGORY_LAW = {
    "phishing": "JL-01", "creds": "JL-02", "elderfin": "JL-03", "stalking": "JL-04",
    "jailbreak": "JL-05", "hiring": "JL-06", "pumpdump": "JL-07", "selfharm": "JL-08",
    "authclaim": "JL-09", "multiturn": "JL-10",
}


def _ensemble_version() -> Optional[str]:
    try:
        from ..ensemble import ENSEMBLE_VERSION
        return ENSEMBLE_VERSION
    except Exception:
        return None


class GovernanceService:
    def __init__(self, default_mode: str = "ensemble", laws_path: Optional[Path] = None) -> None:
        self.default_mode = default_mode
        self.laws_path = Path(laws_path) if laws_path else Path(E.DEFAULT_LAWS)
        raw = self.laws_path.read_bytes()
        self.laws_doc = json.loads(raw)
        self.laws_sha256 = hashlib.sha256(raw).hexdigest()
        self.laws = {law["id"]: law for law in self.laws_doc["laws"]}
        self.model_loaded = False
        self.model_error: Optional[str] = "not loaded yet" if default_mode == "ensemble" else None
        self._lock = threading.Lock()
        self._last_attempt = 0.0

    # ---- model lifecycle -------------------------------------------------------------
    def load_model(self) -> bool:
        """Try to load the classifier once. Safe to call repeatedly; never raises."""
        with self._lock:
            if self.model_loaded:
                return True
            self._last_attempt = time.monotonic()
            try:
                from .. import classifier as C
                if not C.is_available():
                    raise RuntimeError("classifier files or the 'fastembed' package are missing "
                                       "(install jmgl[model]; check JMGL_MODEL_DIR)")
                C.classify("warm-up check", None)
                self.model_loaded, self.model_error = True, None
                log.info("classifier loaded", extra={"event": "model_loaded"})
            except Exception as exc:  # noqa: BLE001 - any failure -> rules-only fallback
                self.model_loaded = False
                self.model_error = f"{type(exc).__name__}: {exc}"[:300]
                log.warning("classifier unavailable; serving rules-only",
                            extra={"event": "model_unavailable", "error": self.model_error})
            return self.model_loaded

    def maybe_retry_model(self, min_interval_s: float = 300.0) -> None:
        if not self.model_loaded and time.monotonic() - self._last_attempt >= min_interval_s:
            self.load_model()

    # ---- evaluation ----------------------------------------------------------------------
    def law_ref(self, law_id: str, source: str) -> dict:
        law = self.laws.get(law_id, {})
        return {"id": law_id, "statement": law.get("statement", ""), "source": source}

    def evaluate(self, action: str, history: list[str], mode: Optional[str] = None,
                 include_signals: bool = False) -> dict[str, Any]:
        requested = mode or self.default_mode
        ctx = {"history": list(history)}
        used, degraded, degraded_reason = requested, False, None
        cl: Optional[dict] = None
        t0 = time.perf_counter()

        verdict = None
        if requested == "ensemble":
            if self.model_loaded:
                try:
                    from .. import classifier as C
                    from ..ensemble import evaluate_action_ensemble
                    verdict = evaluate_action_ensemble(action, ctx, laws_path=self.laws_path)
                    cl = C.classify(action, ctx)  # embedding is cached: no second model pass
                except Exception as exc:  # noqa: BLE001
                    log.exception("ensemble evaluation failed; falling back to rules-only")
                    verdict, cl = None, None
                    degraded_reason = f"ensemble error: {type(exc).__name__}"
            else:
                degraded_reason = self.model_error or "classifier not loaded"
            if verdict is None:
                used, degraded = "rules", True
        if verdict is None:
            verdict = E.evaluate_action(action, ctx, laws_path=self.laws_path)
        eval_s = time.perf_counter() - t0

        laws_triggered = self._laws_triggered(verdict, cl)
        gf = getattr(verdict, "grace_force", None)
        grace = None
        if gf is not None:
            g = getattr(verdict, "grace", None) or {}
            grace = {"score": float(gf), "threshold": g.get("threshold"), "passed": g.get("passed"),
                     "rewritten": g.get("rewritten"),
                     "components": g.get("components", {}) if isinstance(g.get("components"), dict) else {}}
        return {
            "decision": verdict.decision,
            "rule_id": verdict.rule_id,
            "laws_triggered": laws_triggered,
            "reason": verdict.reason,
            "suggested_modification": verdict.suggested_modification,
            "resources": list(verdict.resources),
            "confidence": round(float(cl["prob"]), 4) if cl else None,
            "classifier_category": cl["category"] if cl else None,
            "grace_force": grace,
            "engine": {
                "mode": used, "requested_mode": requested,
                "engine_version": E.ENGINE_VERSION,
                "ensemble_version": _ensemble_version() if used == "ensemble" else None,
                "model_loaded": self.model_loaded, "degraded": degraded,
                "degraded_reason": degraded_reason if degraded else None,
            },
            "signals": dict(verdict.signals) if include_signals else None,
            "_eval_seconds": eval_s,
        }

    def _laws_triggered(self, verdict, cl: Optional[dict]) -> list[dict]:
        out: list[dict] = []
        rid = verdict.rule_id
        if rid == "JL-ML":
            law = CATEGORY_LAW.get((cl or {}).get("category") or verdict.signals.get("classifier_category", ""))
            if law:
                out.append(self.law_ref(law, "classifier"))
        elif rid == "JL-00":
            out.append(self.law_ref(rid, "default"))
        else:
            out.append(self.law_ref(rid, "rules"))
            if rid != "JL-09" and "(JL-09)" in verdict.reason:
                out.append(self.law_ref("JL-09", "rules"))
            if rid == "JL-10":
                for lid in self.laws:
                    if f"({lid}:" in verdict.reason and lid != "JL-10":
                        out.append(self.law_ref(lid, "rules"))
        return out

    def version_info(self) -> dict:
        return {"version": __version__, "engine_version": E.ENGINE_VERSION,
                "ensemble_version": _ensemble_version() or ""}
