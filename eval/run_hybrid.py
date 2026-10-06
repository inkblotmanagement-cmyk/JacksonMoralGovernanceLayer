"""Run rule-only vs hybrid (rules + LocalJudge + fail-closed merge) on one evaluation set.

Usage: python eval/run_hybrid.py --set main|heldout|heldout2|fresh|probe|sample100k [--n 5000] [--seed 7]

Writes one JSON line per case to eval/hybrid_runs/<set>.jsonl as it goes (resumable: cases whose id
is already present are skipped on restart). Merged audit records go to eval/hybrid_runs/audit_<set>.jsonl.
sample100k = stratified random sample (proportional per category, fixed seed) of eval/cases_100k.jsonl.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from jmgl import evaluate_action  # noqa: E402
from jmgl.judge import LOCAL_PROMPT_VERSION, judge_to_four_way, make_judge, parse_and_validate, run_judge  # noqa: E402
from jmgl.merge import merge  # noqa: E402

OUT = ROOT / "eval/hybrid_runs"
TEST_SETS = {"main": "tests/tests.json", "heldout": "tests/heldout.json", "heldout2": "tests/heldout2.json",
             "fresh": "tests/fresh_handwritten.json", "probe": "tests/probe_posthoc.json"}


def load_cases(name, n, seed):
    if name in TEST_SETS:
        raw = json.loads((ROOT / TEST_SETS[name]).read_text())["cases"]
        out = []
        for i, c in enumerate(raw):
            exp = c["expected"] if isinstance(c["expected"], list) else [c["expected"]]
            cat = c.get("category") or {"ESCALATE": "self_harm", "BLOCK": "harm_other", "ALLOW": "control"}[exp[0]]
            out.append({"id": c.get("id") or f"P{i+1:02d}", "text": c["request"],
                        "history": (c.get("context") or {}).get("history"), "category": cat, "expected": exp})
        return out
    if name == "sample100k":
        by_cat = defaultdict(list)
        with open(ROOT / "eval/cases_100k.jsonl") as f:
            for line in f:
                c = json.loads(line)
                by_cat[c["category"]].append(c)
        total = sum(len(v) for v in by_cat.values())
        rng = random.Random(seed)
        # proportional allocation with largest-remainder rounding
        quotas = {k: n * len(v) / total for k, v in by_cat.items()}
        alloc = {k: int(q) for k, q in quotas.items()}
        for k in sorted(quotas, key=lambda k: -(quotas[k] - alloc[k]))[: n - sum(alloc.values())]:
            alloc[k] += 1
        out = []
        for k in sorted(by_cat):
            for c in rng.sample(by_cat[k], alloc[k]):
                out.append({"id": c["id"], "text": c["text"], "history": c.get("history"),
                            "category": c["category"], "expected": c["expected"], "template_id": c["template_id"]})
        return out
    raise SystemExit(f"unknown set {name}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", required=True)
    ap.add_argument("--n", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--judge", default="local")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    out_path = OUT / f"{args.set}.jsonl"
    audit = OUT / f"audit_{args.set}.jsonl"
    done = set()
    if out_path.exists():
        done = {json.loads(l)["id"] for l in out_path.read_text().splitlines() if l.strip()}
    cases = [c for c in load_cases(args.set, args.n, args.seed) if c["id"] not in done]
    print(f"{args.set}: {len(done)} already done, {len(cases)} to run", flush=True)
    if not cases:
        return
    judge = make_judge(args.judge)
    with out_path.open("a") as fo:
        for c in cases:
            ctx = {"history": c["history"]} if c.get("history") else {}
            t0 = time.perf_counter()
            rv = evaluate_action(c["text"], ctx or None)
            t1 = time.perf_counter()
            jr = run_judge(judge, c["text"], {"history": c.get("history") or [], "training": False,
                                              "consensual_share": False})
            t2 = time.perf_counter()
            fv = merge(rv, jr.raw, jr.error, ctx, request=c["text"], audit_path=audit, judge_name=judge.name)
            jobj = parse_and_validate(jr.raw)[0] if jr.raw is not None and not jr.error else None
            rec = {**{k: c[k] for k in ("id", "category", "expected")},
                   "template_id": c.get("template_id"),
                   "rule_decision": rv.decision, "rule_id": rv.rule_id,
                   "judge_status": fv.judge_status, "judge_decision": fv.judge_decision,
                   "judge_category": fv.judge_category, "judge_four_way": judge_to_four_way(jobj),
                   "judge_error": fv.judge_error, "judge_rationale": fv.judge_rationale,
                   "gate": fv.decision, "four_way": fv.four_way, "decided_by": fv.decided_by,
                   "crisis": fv.crisis, "has_988": any("988" in r for r in fv.resources),
                   "rule_s": round(t1 - t0, 5), "judge_s": round(t2 - t1, 3),
                   "prompt_version": LOCAL_PROMPT_VERSION}
            fo.write(json.dumps(rec) + "\n")
            fo.flush()


if __name__ == "__main__":
    main()
