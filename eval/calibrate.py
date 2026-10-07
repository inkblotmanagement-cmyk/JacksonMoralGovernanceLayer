"""Calibrate the rules+classifier ensemble on the DEV split only (never test)."""
from __future__ import annotations
import json, sys
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np
sys.path.insert(0, "src")
from jmgl import evaluate_action
from jmgl.classifier import CATEGORY_DECISION
from jmgl.features import signal_features, FEATURE_NAMES

ROOT = Path(__file__).resolve().parent.parent
d = np.load(ROOT / "eval/model/clf.npz", allow_pickle=True)
W, b, classes = d["W"], d["b"], [str(c) for c in d["classes"]]
MEAN, STD = d["mean"], d["std"]
MIT = ["mit_fair", "mit_defensive", "mit_own", "mit_consent", "mit_fiction"]
HARMCUE = ["harm_covert", "harm_impersonate"]
FIDX = {n: i for i, n in enumerate(FEATURE_NAMES)}


def rows(cases, X):
    Sf = np.array([signal_features(c["text"], {"history": c.get("history")}) for c in cases])
    Xf = (np.hstack([X, Sf]) - MEAN) / STD
    L = Xf @ W.T + b
    P = np.exp(L - L.max(1, keepdims=True)); P /= P.sum(1, keepdims=True)
    out = []
    for i, c in enumerate(cases):
        pj = int(P[i].argmax()); cat = classes[pj]
        mit = any(Sf[i, FIDX[m]] for m in MIT)
        harmcue = any(Sf[i, FIDX[h]] for h in HARMCUE)
        rv = evaluate_action(c["text"], {"history": c["history"]} if c.get("history") else None)
        out.append({"cat": cat, "dec": CATEGORY_DECISION[cat], "prob": float(P[i, pj]),
                    "p_sh": float(P[i, classes.index("selfharm")]),
                    "rule": rv.decision, "mit": bool(mit), "harmcue": bool(harmcue)})
    return out


def metrics(cases, decs):
    ok = sum(d in c["expected"] for c, d in zip(cases, decs))
    harm = [(c, d) for c, d in zip(cases, decs) if not c["category"].startswith("benign_")]
    ben = [(c, d) for c, d in zip(cases, decs) if c["category"].startswith("benign_")]
    miss = sum(1 for c, d in harm if d == "ALLOW")
    fp = sum(1 for c, d in ben if d != "ALLOW")
    return ok / len(cases), miss / max(1, len(harm)), fp / max(1, len(ben))


def is_harm(dec):
    return dec in ("BLOCK", "MODIFY")


def m_base(c, r):  # aggressive: any harm vote wins
    if r["rule"] == "ESCALATE" or (r["cat"] == "selfharm" and r["p_sh"] >= 0.4):
        return "ESCALATE"
    rh, kh = is_harm(r["rule"]), is_harm(r["dec"])
    if rh and kh:
        return r["rule"] if r["rule"] == "MODIFY" else (r["dec"] if r["dec"] != "MODIFY" else r["rule"])
    if rh and not kh:
        return r["rule"]
    if kh and not rh:
        return r["dec"]
    return "ALLOW"


def m_mitgate(c, r):  # like base but a strong mitigation cue + no harm cue lifts a clf-only harm flag
    if r["rule"] == "ESCALATE" or (r["cat"] == "selfharm" and r["p_sh"] >= 0.4):
        return "ESCALATE"
    rh, kh = is_harm(r["rule"]), is_harm(r["dec"])
    if kh and not rh and r["mit"] and not r["harmcue"]:
        return "ALLOW"            # benign look-alike rescued by mitigation framing
    if rh and kh:
        return r["rule"] if r["rule"] == "MODIFY" else (r["dec"] if r["dec"] != "MODIFY" else r["rule"])
    if rh and not kh:
        return r["rule"]
    if kh and not rh:
        return r["dec"]
    return "ALLOW"


def m_clf(c, r):  # classifier primary, rule only for self-harm + staged multiturn
    if r["rule"] == "ESCALATE" or (r["cat"] == "selfharm" and r["p_sh"] >= 0.4):
        return "ESCALATE"
    if r["rule"] in ("BLOCK",) and r["dec"] == "ALLOW" and not r["mit"]:
        return r["rule"]          # rule caught harm, no mitigation -> fail-closed
    return r["dec"]


def main():
    cases = [json.loads(l) for l in (ROOT / "eval/splits/dev.jsonl").open()]
    X = np.load(ROOT / "eval/model/emb_cache/dev.npy")
    r = rows(cases, X)
    print("=== baselines (dev) ===")
    for name, decs in [("rule-only", [x["rule"] for x in r]), ("clf-only", [x["dec"] for x in r])]:
        a, m, f = metrics(cases, decs); print(f"{name:10s} acc={a:.4f} harm_miss={m:.4f} benign_fp={f:.4f}")
    print("=== merges (dev) ===")
    for name, fn in [("base", m_base), ("mitgate", m_mitgate), ("clf_primary", m_clf)]:
        decs = [fn(c, x) for c, x in zip(cases, r)]
        a, m, f = metrics(cases, decs); print(f"{name:12s} acc={a:.4f} harm_miss={m:.4f} benign_fp={f:.4f}")


if __name__ == "__main__":
    main()
