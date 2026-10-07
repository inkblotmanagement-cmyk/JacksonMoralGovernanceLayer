"""Evaluate rule-only vs classifier-only vs ensemble on held-out and fresh sets.

Writes eval/accuracy_results.json. Decision = first/primary four-way label; a
case is correct if the decision is in its accepted 'expected' set.
"""
from __future__ import annotations
import json, sys, time
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np
sys.path.insert(0, "src")
from jmgl import evaluate_action
from jmgl.ensemble import evaluate_action_ensemble
from jmgl import classifier as C

ROOT = Path(__file__).resolve().parent.parent
DECS = ["ALLOW", "BLOCK", "MODIFY", "ESCALATE"]


def load_jsonl(p):
    return [json.loads(l) for l in Path(p).open()]


def load_testset(p):
    d = json.loads(Path(p).read_text())
    cases = d["cases"] if isinstance(d, dict) else d
    out = []
    for c in cases:
        out.append({"text": c.get("text") or c.get("request"),
                    "expected": c["expected"] if isinstance(c["expected"], list) else [c["expected"]],
                    "category": c.get("category", "?"),
                    "history": (c.get("context") or {}).get("history") or c.get("history")})
    return out


def ctx(c):
    return {"history": c["history"]} if c.get("history") else None


def evalset(name, cases, systems):
    res = {"n": len(cases)}
    for sysname, fn in systems.items():
        decs = []
        t0 = time.perf_counter()
        for c in cases:
            decs.append(fn(c["text"], ctx(c)).decision)
        dt = time.perf_counter() - t0
        ok = sum(d in c["expected"] for c, d in zip(cases, decs))
        harm = [(c, d) for c, d in zip(cases, decs) if not c["category"].startswith("benign_")]
        ben = [(c, d) for c, d in zip(cases, decs) if c["category"].startswith("benign_")]
        miss = sum(1 for c, d in harm if d == "ALLOW")
        fp = sum(1 for c, d in ben if d != "ALLOW")
        # confusion over primary expected decision
        conf = defaultdict(Counter)
        for c, d in zip(cases, decs):
            conf[c["expected"][0]][d] += 1
        res[sysname] = {
            "accuracy": ok / len(cases),
            "harm_n": len(harm), "harm_miss_rate": miss / max(1, len(harm)),
            "benign_n": len(ben), "benign_fp_rate": fp / max(1, len(ben)),
            "latency_ms_per_case": 1000 * dt / len(cases),
            "confusion_primary": {k: dict(v) for k, v in conf.items()},
        }
    return res


def main():
    systems = {
        "rule_only": evaluate_action,
        "ensemble": evaluate_action_ensemble,
    }
    print("classifier available:", C.is_available())
    sets = {
        "heldout_test_template_disjoint": load_jsonl(ROOT / "eval/splits/test.jsonl"),
        "heldout_test_random": load_jsonl(ROOT / "eval/splits/random_test.jsonl"),
        "fresh_paraphrase": load_testset(ROOT / "tests/fresh_paraphrase.json"),
        "fresh_handwritten": load_testset(ROOT / "tests/fresh_handwritten.json"),
        "heldout1": load_testset(ROOT / "tests/heldout.json"),
        "heldout2": load_testset(ROOT / "tests/heldout2.json"),
        "probe": load_testset(ROOT / "tests/probe_posthoc.json"),
    }
    out = {}
    for name, cases in sets.items():
        print("evaluating", name, len(cases), "...", flush=True)
        out[name] = evalset(name, cases, systems)
        for s in systems:
            r = out[name][s]
            print(f"  {s:10s} acc={r['accuracy']:.4f} harm_miss={r['harm_miss_rate']:.4f} "
                  f"benign_fp={r['benign_fp_rate']:.4f} lat={r['latency_ms_per_case']:.1f}ms")
    (ROOT / "eval/accuracy_results.json").write_text(json.dumps(out, indent=1))
    print("wrote eval/accuracy_results.json")


if __name__ == "__main__":
    main()
