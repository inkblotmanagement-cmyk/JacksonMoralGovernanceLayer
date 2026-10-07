"""JMGL learned category classifier (sentence embeddings + logistic regression).

This is an ADDITIONAL signal, not a replacement for the deterministic rules. It
predicts a scenario CATEGORY and a calibrated-ish probability; jmgl.ensemble
combines it with the rule engine under a fail-closed policy.

Inference is numpy-only (logits = X @ W.T + b, softmax). The sentence embeddings
come from BAAI/bge-small-en-v1.5 (Apache-2.0, 384-d) via fastembed/onnxruntime,
loaded lazily and cached as a process-global singleton. Model weights live in
eval/model/clf.npz (+ clf_meta.json); the embedding model is downloaded to the
HuggingFace cache on first use (never committed), mirroring the local-judge setup.

If the model files or fastembed are missing, is_available() returns False and the
engine falls back to rules only (no crash, fail-closed).
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Optional
import numpy as np

from .features import signal_features

ROOT = Path(__file__).resolve().parents[2]
MODEL_DIR = ROOT / "eval" / "model"
NPZ = MODEL_DIR / "clf.npz"
META = MODEL_DIR / "clf_meta.json"

# category -> primary four-way decision. Where the generator accepts two
# decisions (hiring: BLOCK|MODIFY, multiturn: BLOCK|ESCALATE) we pick the one the
# rule engine already uses, so the two stages agree.
CATEGORY_DECISION = {
    "benign_auth": "ALLOW", "benign_crypto": "ALLOW", "benign_elder": "ALLOW",
    "benign_fiction": "ALLOW", "benign_hiring": "ALLOW", "benign_locate": "ALLOW",
    "benign_multi": "ALLOW", "benign_phish": "ALLOW", "benign_secure": "ALLOW",
    "benign_vent": "ALLOW",
    "selfharm": "ESCALATE",
    "hiring": "MODIFY",
    "multiturn": "BLOCK",
    "phishing": "BLOCK", "creds": "BLOCK", "elderfin": "BLOCK", "stalking": "BLOCK",
    "jailbreak": "BLOCK", "pumpdump": "BLOCK", "authclaim": "BLOCK",
}

_STATE = {"loaded": False, "W": None, "b": None, "classes": None,
          "mean": None, "std": None, "embedder": None, "meta": None}


def is_available() -> bool:
    if not (NPZ.exists() and META.exists()):
        return False
    try:
        import fastembed  # noqa: F401
    except Exception:
        return False
    return True


def _load():
    if _STATE["loaded"]:
        return
    import os
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    from fastembed import TextEmbedding
    d = np.load(NPZ, allow_pickle=True)
    meta = json.loads(META.read_text())
    _STATE.update(W=d["W"].astype(np.float32), b=d["b"].astype(np.float32),
                  classes=[str(c) for c in d["classes"]],
                  mean=d["mean"].astype(np.float32), std=d["std"].astype(np.float32),
                  embedder=TextEmbedding(model_name=meta["embed_model"]),
                  meta=meta, loaded=True)


def _embed(text: str) -> np.ndarray:
    _load()
    return np.asarray(list(_STATE["embedder"].embed([text]))[0], dtype=np.float32)


def _features(request: str, context: Optional[dict]) -> np.ndarray:
    context = context or {}
    history = [str(h) for h in (context.get("history") or [])]
    text = " ".join(history + [request]) if history else request
    emb = _embed(text)
    sig = signal_features(request, context)
    x = np.concatenate([emb, sig]).astype(np.float32)
    return (x - _STATE["mean"]) / _STATE["std"]


def classify(request: str, context: Optional[dict] = None) -> dict:
    """Return {category, decision, prob, probs} for the request (+ history)."""
    _load()
    x = _features(request, context)
    logits = x @ _STATE["W"].T + _STATE["b"]
    logits -= logits.max()
    p = np.exp(logits)
    p /= p.sum()
    i = int(p.argmax())
    cat = _STATE["classes"][i]
    return {
        "category": cat,
        "decision": CATEGORY_DECISION.get(cat, "BLOCK"),
        "prob": float(p[i]),
        "probs": {c: float(pr) for c, pr in zip(_STATE["classes"], p)},
    }
