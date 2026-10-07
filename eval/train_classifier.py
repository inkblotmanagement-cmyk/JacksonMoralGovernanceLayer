"""Train the JMGL category classifier (sentence embeddings + logistic regression).

Honest protocol
---------------
* Trains ONLY on eval/splits/train.jsonl (template-disjoint train).
* Selects the LR regularization strength C ONLY on eval/splits/dev.jsonl.
* Never reads test.jsonl here.
* Saves a numpy-only artifact (eval/model/clf.npz + clf_meta.json) so inference
  needs only numpy + fastembed, not scikit-learn.

Model: BAAI/bge-small-en-v1.5 (384-d, Apache-2.0, ~130 MB, CPU, via fastembed /
onnxruntime). Classifier: multinomial logistic regression. The classifier
predicts a scenario CATEGORY; jmgl.classifier maps category -> four-way decision.

Usage: python eval/train_classifier.py
"""
from __future__ import annotations
import json, os
from pathlib import Path
import numpy as np
import sys as _sys
_sys.path.insert(0, str((__import__('pathlib').Path(__file__).resolve().parent.parent/'src')))
from jmgl.features import signal_features

os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
ROOT = Path(__file__).resolve().parent.parent
SP = ROOT / "eval/splits"
MODEL_DIR = ROOT / "eval/model"
EMB_MODEL = "BAAI/bge-small-en-v1.5"


def emb_text(c):
    if c.get("history"):
        return " ".join(c["history"] + [c["text"]])
    return c["text"]


def load(name):
    return [json.loads(l) for l in (SP / f"{name}.jsonl").open()]


def embed_all(texts, embedder):
    # fastembed returns normalized vectors; batch for memory
    out = []
    B = 1024
    for i in range(0, len(texts), B):
        out.extend(embedder.embed(texts[i:i + B]))
    return np.asarray(out, dtype=np.float32)


CACHE = ROOT / "eval/model/emb_cache"


def embed_cached(name, texts, embedder):
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"{name}.npy"
    if f.exists():
        X = np.load(f)
        if X.shape[0] == len(texts):
            return X
    X = embed_all(texts, embedder)
    np.save(f, X)
    return X


def main():
    from fastembed import TextEmbedding
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import accuracy_score

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    embedder = TextEmbedding(model_name=EMB_MODEL)

    train, dev = load("train"), load("dev")
    Etr = embed_cached("train", [emb_text(c) for c in train], embedder)
    Edv = embed_cached("dev", [emb_text(c) for c in dev], embedder)
    Str_ = np.array([signal_features(c["text"], {"history": c.get("history")}) for c in train])
    Sdv = np.array([signal_features(c["text"], {"history": c.get("history")}) for c in dev])
    Xtr = np.hstack([Etr, Str_]).astype(np.float32)
    Xdv = np.hstack([Edv, Sdv]).astype(np.float32)
    ytr = np.array([c["category"] for c in train])
    ydv = np.array([c["category"] for c in dev])
    # standardize (fit on train only)
    mean = Xtr.mean(0); std = Xtr.std(0); std[std < 1e-6] = 1.0
    Xtr = (Xtr - mean) / std
    Xdv = (Xdv - mean) / std
    print("train", Xtr.shape, "dev", Xdv.shape)

    best = None
    for C in (0.5, 1, 2, 4, 8, 16):
        clf = LogisticRegression(C=C, max_iter=2000, n_jobs=-1)
        clf.fit(Xtr, ytr)
        acc = accuracy_score(ydv, clf.predict(Xdv))
        print(f"C={C:<4} dev category acc={acc:.4f}")
        if best is None or acc > best[1]:
            best = (C, acc, clf)
    C, acc, clf = best
    print(f"selected C={C} dev category acc={acc:.4f}")

    np.savez(MODEL_DIR / "clf.npz",
             W=clf.coef_.astype(np.float32), b=clf.intercept_.astype(np.float32),
             classes=np.array(clf.classes_),
             mean=mean.astype(np.float32), std=std.astype(np.float32))
    meta = {
        "embed_model": EMB_MODEL,
        "classes": list(clf.classes_),
        "C": C,
        "dev_category_accuracy": acc,
        "features": "bge-small-en-v1.5 (384) + jmgl signal features (26), standardized",
        "trained_on": "eval/splits/train.jsonl (template-disjoint)",
        "note": "numpy-only inference: logits = X @ W.T + b, softmax over classes.",
    }
    (MODEL_DIR / "clf_meta.json").write_text(json.dumps(meta, indent=1))
    print("saved", MODEL_DIR / "clf.npz")


if __name__ == "__main__":
    main()
