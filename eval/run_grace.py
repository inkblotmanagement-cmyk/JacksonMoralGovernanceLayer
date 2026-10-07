"""Evaluate Grace Force (0.7 pass line + rewrite path) on held-out + fresh sets.

Reports, per set: accuracy at the configured threshold, harm-miss, benign
false-positive, a threshold sweep (score separation), rewrite success, and the
laundering rate on the red-team set. Writes eval/grace_results.json.

Large synthetic sets are sampled (stratified by category) for speed; sample size
and seed are recorded. Nothing here tunes the score (constants were set on dev).
"""
from __future__ import annotations
import json, random, sys, time
from collections import Counter, defaultdict
from pathlib import Path
sys.path.insert(0, "src")
from jmgl.grace import evaluate_grace_force, load_config

ROOT = Path(__file__).resolve().parent.parent
CFG = load_config()
THR = CFG["threshold_pass"]
SWEEP = [0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9]


def load_jsonl(p, sample=None, seed=7):
    cases = [json.loads(l) for l in Path(p).open()]
    if sample and len(cases) > sample:
        by = defaultdict(list)
        for c in cases:
            by[c["category"]].append(c)
        rng = random.Random(seed)
        out = []
        frac = sample / len(cases)
        for cat, cs in by.items():
            rng.shuffle(cs)
            out.extend(cs[: max(1, round(len(cs) * frac))])
        rng.shuffle(out)
        return out
    return cases


def load_set(p):
    d = json.loads(Path(p).read_text())
    cases = d["cases"] if isinstance(d, dict) else d
    out = []
    for c in cases:
        out.append({"text": c.get("text") or c.get("request"),
                    "expected": c["expected"] if isinstance(c.get("expected"), list) else ([c["expected"]] if c.get("expected") else None),
                    "category": c.get("category", "?"),
                    "history": (c.get("context") or {}).get("history") or c.get("history")})
    return out


def ctx(c):
    return {"history": c["history"]} if c.get("history") else None


def run(name, cases, laundering=False):
    t0 = time.time()
    rows = []
    for c in cases:
        v = evaluate_grace_force(c["text"], ctx(c))
        g = v.grace or {}
        rows.append({"cat": c["category"], "expected": c.get("expected"),
                     "decision": v.decision, "rule_id": v.rule_id,
                     "gf": g.get("original_grace_force", v.grace_force),
                     "final_gf": v.grace_force, "rewritten": g.get("rewritten", False),
                     "benign": c["category"].startswith("benign_")})
    dt = time.time() - t0
    res = {"n": len(rows), "latency_ms_per_case": 1000 * dt / max(1, len(rows))}

    if laundering:
        bad = [r for r in rows if r["decision"] in ("ALLOW",) or (r["decision"] == "MODIFY" and r["rewritten"])]
        res["laundered_pass"] = len(bad)
        res["laundered_rate"] = len(bad) / len(rows)
        res["decisions"] = dict(Counter(r["decision"] for r in rows))
        return res, rows

    scored = [r for r in rows if r["expected"]]
    if scored:
        ok = sum(r["decision"] in r["expected"] for r in scored)
        harm = [r for r in scored if not r["benign"]]
        ben = [r for r in scored if r["benign"]]
        res["accuracy_at_threshold"] = ok / len(scored)
        res["harm_miss_rate"] = sum(r["decision"] == "ALLOW" for r in harm) / max(1, len(harm))
        res["benign_fp_rate"] = sum(r["decision"] != "ALLOW" for r in ben) / max(1, len(ben))
        res["decision_counts"] = dict(Counter(r["decision"] for r in scored))
    # score-only separation sweep
    harm_gf = [r["gf"] for r in rows if not r["benign"]]
    ben_gf = [r["gf"] for r in rows if r["benign"]]
    res["sweep"] = {str(t): {
        "harm_miss": round(sum(g >= t for g in harm_gf) / max(1, len(harm_gf)), 4),
        "benign_fp": round(sum(g < t for g in ben_gf) / max(1, len(ben_gf)), 4),
    } for t in SWEEP}
    # rewrite stats
    rw = [r for r in rows if r["gf"] < THR and r["decision"] != "BLOCK" and r["rule_id"] != "JL-08"]
    res["rewrite"] = {
        "below_threshold_non_block": len(rw),
        "benign_below": sum(1 for r in rw if r["benign"]),
        "benign_rewritten_pass": sum(1 for r in rw if r["benign"] and r["rewritten"]),
        "harm_below": sum(1 for r in rw if not r["benign"]),
        "harm_rewritten_pass": sum(1 for r in rw if not r["benign"] and r["rewritten"]),
    }
    return res, rows


def main():
    sets = {
        "heldout_test_template_disjoint_sample": load_jsonl(ROOT / "eval/splits/test.jsonl", sample=3000),
        "fresh_paraphrase": load_set(ROOT / "tests/fresh_paraphrase.json"),
        "fresh_handwritten": load_set(ROOT / "tests/fresh_handwritten.json"),
    }
    out = {"config": {"threshold": THR, "weights": CFG["weights"]}}
    all_rows = {}
    for name, cases in sets.items():
        print("evaluating", name, len(cases), "...", flush=True)
        res, rows = run(name, cases)
        out[name] = res
        all_rows[name] = rows
        print(f"  acc@{THR}={res.get('accuracy_at_threshold'):.4f} harm_miss={res.get('harm_miss_rate'):.4f} "
              f"benign_fp={res.get('benign_fp_rate'):.4f} lat={res['latency_ms_per_case']:.0f}ms")
        print("  rewrite:", res["rewrite"])
    print("evaluating grace_redteam ...", flush=True)
    rt, _ = run("redteam", load_set(ROOT / "tests/grace_redteam.json"), laundering=True)
    out["grace_redteam"] = rt
    print("  laundered_pass:", rt["laundered_pass"], "/", rt["n"], "decisions:", rt["decisions"])
    (ROOT / "eval/grace_results.json").write_text(json.dumps(out, indent=1))
    print("wrote eval/grace_results.json")


if __name__ == "__main__":
    main()
