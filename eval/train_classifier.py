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
    import argparse
    from fastembed import TextEmbedding
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import accuracy_score

    ap = argparse.ArgumentParser()
    ap.add_argument("--augment", default=None,
                    help="Optional JSONL of TRAIN-ONLY augmentation cases to append.")
    args = ap.parse_args()

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    embedder = TextEmbedding(model_name=EMB_MODEL)

    train, dev = load("train"), load("dev")
    n_base = len(train)
    aug_n = 0
    if args.augment:
        # Exact-dedup augmentation against EVERY eval split (train/dev/test) so no
        # test/dev surface string can leak into training via augmentation.
        seen = set()
        for nm in ("train", "dev", "test"):
            for c in load(nm):
                seen.add(emb_text(c).strip())
        aug = [json.loads(l) for l in Path(args.augment).open()]
        kept = [c for c in aug if emb_text(c).strip() not in seen]
        aug_n = len(kept)
        print(f"augment: {len(aug)} given, {aug_n} kept after exact-dedup vs train/dev/test "
              f"({len(aug)-aug_n} dropped); train {n_base} -> {n_base + aug_n}")
    Etr = embed_cached("train", [emb_text(c) for c in train], embedder)
    if aug_n:
        # embed augmentation separately (own cache) and concatenate, so the base
        # train embedding cache stays valid.
        import hashlib
        key = "augment_" + hashlib.md5(("".join(emb_text(c) for c in kept)).encode()).hexdigest()[:10]
        Eaug = embed_cached(key, [emb_text(c) for c in kept], embedder)
        Etr = np.vstack([Etr, Eaug])
        train = train + kept
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
        "trained_on": "eval/splits/train.jsonl (template-disjoint)" + (f" + {aug_n} augmentation cases (train-only, dedup vs all splits)" if aug_n else ""),
        "augmentation_cases": aug_n,
        "note": "numpy-only inference: logits = X @ W.T + b, softmax over classes.",
    }
    (MODEL_DIR / "clf_meta.json").write_text(json.dumps(meta, indent=1))
    print("saved", MODEL_DIR / "clf.npz")


if __name__ == "__main__":
    main()
