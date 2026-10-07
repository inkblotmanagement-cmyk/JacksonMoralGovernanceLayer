"""Score stability: determinism + robustness to light edits.

1. Determinism: evaluate each sampled request twice and confirm the gate score and
   decision are byte-identical (the engine is deterministic; this proves it).
2. Robustness: apply ~3 light edits per item (typo, casing, punctuation, synonym
   swap) to a ~300-item stratified sample and report the gate-score std dev and the
   decision flip rate vs the unedited item.

Usage: python eval/stability.py [--sample 300] [--edits 3]
"""
from __future__ import annotations
import argparse, json, random, statistics, sys
from collections import defaultdict
from pathlib import Path
sys.path.insert(0, "src")
from jmgl.grace import evaluate_grace_force

ROOT = Path(__file__).resolve().parent.parent
SYN = {"help": "assist", "email": "message", "account": "login", "find": "locate",
       "please": "pls", "photos": "pics", "message": "msg", "phone": "mobile",
       "password": "passphrase", "address": "home address", "money": "cash",
       "quickly": "fast", "without": "w/o", "because": "cuz", "friend": "buddy",
       "want": "wanna", "going to": "gonna", "need": "gotta have"}


def gather(sample, seed=13):
    pool = []
    for l in (ROOT / "eval/splits/test.jsonl").open():
        c = json.loads(l); pool.append((c["text"], c["category"], None))
    for fn in ["fresh_handwritten", "fresh_paraphrase", "selfharm_consent_heldout", "multiturn_heldout"]:
        d = json.loads((ROOT / f"tests/{fn}.json").read_text())
        for c in (d["cases"] if isinstance(d, dict) else d):
            pool.append((c.get("text") or c.get("request"), c.get("category", "?"), c.get("history")))
    by = defaultdict(list)
    for item in pool:
        by[item[1]].append(item)
    rng = random.Random(seed); out = []; frac = sample / len(pool)
    for cat, items in by.items():
        rng.shuffle(items); out.extend(items[: max(1, round(len(items) * frac))])
    rng.shuffle(out); return out[:sample]


def typo(t, rng):
    ws = t.split()
    if not ws:
        return t
    i = rng.randrange(len(ws)); w = ws[i]
    if len(w) > 3:
        j = rng.randrange(len(w) - 1)
        w = w[:j] + w[j + 1] + w[j] + w[j + 2:]  # swap adjacent chars
    ws[i] = w; return " ".join(ws)


def recase(t, rng):
    return rng.choice([t.upper(), t.lower(), t.title(), t.capitalize()])


def repunct(t, rng):
    t = t.rstrip(".!?")
    return t + rng.choice(["", ".", "...", "!", " ?", ","])


def synswap(t, rng):
    low = t
    for k, v in SYN.items():
        if k in low.lower():
            import re
            return re.sub(re.escape(k), v, low, count=1, flags=re.I)
    return low


EDITS = [typo, recase, repunct, synswap]


def gate_dec(text, history):
    ctx = {"history": history} if history else None
    v = evaluate_grace_force(text, ctx)
    return (v.grace or {}).get("original_gate_score"), v.decision


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=300)
    ap.add_argument("--edits", type=int, default=3)
    a = ap.parse_args()
    items = gather(a.sample)
    rng = random.Random(99)

    # 1) determinism
    nondet = 0
    base = {}
    for i, (text, cat, hist) in enumerate(items):
        g1, d1 = gate_dec(text, hist); g2, d2 = gate_dec(text, hist)
        if g1 != g2 or d1 != d2:
            nondet += 1
        base[i] = (g1, d1)

    # 2) robustness under light edits
    per_item_std, flips, total_variants = [], 0, 0
    for i, (text, cat, hist) in enumerate(items):
        g0, d0 = base[i]
        scores = [g0]
        for _ in range(a.edits):
            fn = EDITS[rng.randrange(len(EDITS))]
            variant = fn(text, rng)
            g, d = gate_dec(variant, hist)
            scores.append(g); total_variants += 1
            if d != d0:
                flips += 1
        per_item_std.append(statistics.pstdev(scores) if len(scores) > 1 else 0.0)

    res = {
        "sample": len(items), "edits_per_item": a.edits,
        "determinism_nonreproducible": nondet,
        "determinism_ok": nondet == 0,
        "mean_gate_std_within_item": round(statistics.mean(per_item_std), 4),
        "max_gate_std_within_item": round(max(per_item_std), 4),
        "variants_total": total_variants,
        "decision_flips": flips,
        "decision_flip_rate": round(flips / max(1, total_variants), 4),
    }
    (ROOT / "eval/stability_results.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
