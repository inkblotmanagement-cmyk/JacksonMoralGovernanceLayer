"""Run JMGL over eval/cases_100k.jsonl and write eval/results_100k.json + eval/REPORT.md.

Usage: python eval/run_eval.py [--cases eval/cases_100k.jsonl] [--chunk 10000]
Engine, rules and laws.json are used as-is (clean baseline). Results are
streamed: per-chunk progress is appended to eval/run_progress.log.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from jmgl import evaluate_action, ENGINE_VERSION  # noqa: E402

HARM_PRIORITY = ["selfharm", "stalking"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default=str(ROOT / "eval/cases_100k.jsonl"))
    ap.add_argument("--chunk", type=int, default=10000)
    args = ap.parse_args()

    progress = ROOT / "eval/run_progress.log"
    progress.write_text("")
    cat_n, cat_pass = Counter(), Counter()
    cat_dist = defaultdict(Counter)
    cat_rules = defaultdict(Counter)
    tpl_n, tpl_pass = Counter(), Counter()
    tpl_cat = {}
    misses_by_cat = defaultdict(list)  # keep first few per category
    total = passed = 0
    benign_n = benign_blocked = benign_nonallow = 0
    harm_n = harm_allowed = 0

    t0 = time.perf_counter()
    with open(args.cases) as f:
        for line in f:
            c = json.loads(line)
            ctx = {"history": c["history"]} if c.get("history") else None
            v = evaluate_action(c["text"], ctx)
            d = v.decision
            ok = d in c["expected"]
            cat, tid = c["category"], c["template_id"]
            total += 1
            passed += ok
            cat_n[cat] += 1
            cat_pass[cat] += ok
            cat_dist[cat][d] += 1
            cat_rules[cat][v.rule_id or "none"] += 1
            tpl_n[tid] += 1
            tpl_pass[tid] += ok
            tpl_cat[tid] = cat
            benign = cat.startswith("benign_")
            if benign:
                benign_n += 1
                benign_blocked += d == "BLOCK"
                benign_nonallow += d != "ALLOW"
            else:
                harm_n += 1
                harm_allowed += d == "ALLOW"
            if not ok and len(misses_by_cat[cat]) < 25:
                misses_by_cat[cat].append({"id": c["id"], "text": c["text"], "history": c.get("history"),
                                           "category": cat, "template_id": tid, "got": d,
                                           "rule_id": v.rule_id, "expected": c["expected"]})
            if total % args.chunk == 0:
                with progress.open("a") as p:
                    p.write(f"{total} done, pass={passed/total:.4f}, {time.perf_counter()-t0:.1f}s\n")
    elapsed = time.perf_counter() - t0

    per_cat = {c: {"n": cat_n[c], "pass_rate": cat_pass[c] / cat_n[c],
                   "verdicts": dict(cat_dist[c]), "rule_ids": dict(cat_rules[c].most_common(6))}
               for c in sorted(cat_n)}
    tpls = sorted(({"template_id": t, "category": tpl_cat[t], "n": tpl_n[t],
                    "pass_rate": tpl_pass[t] / tpl_n[t]} for t in tpl_n),
                  key=lambda r: (r["pass_rate"], r["template_id"]))
    sh = cat_dist["selfharm"]
    sh_n = cat_n["selfharm"]
    stats_path = ROOT / "eval/generation_stats.json"
    gen_stats = json.loads(stats_path.read_text()) if stats_path.exists() else None

    # example misses: self-harm, stalking first, then false blocks, then others
    examples = []
    for c in HARM_PRIORITY:
        examples += misses_by_cat.get(c, [])[:3]
    fb = [m for c, ms in misses_by_cat.items() if c.startswith("benign_") for m in ms if m["got"] == "BLOCK"]
    examples += fb[:3]
    for c, ms in sorted(misses_by_cat.items()):
        for m in ms[:1]:
            if m not in examples:
                examples.append(m)
    examples = examples[:10]

    res = {
        "engine_version": ENGINE_VERSION,
        "n": total, "overall_pass_rate": passed / total,
        "benign": {"n": benign_n, "false_block_rate": benign_blocked / benign_n,
                   "non_allow_rate": benign_nonallow / benign_n},
        "harm": {"n": harm_n, "missed_harm_rate_allow": harm_allowed / harm_n},
        "selfharm": {"n": sh_n, "allow_share": sh["ALLOW"] / sh_n if sh_n else None,
                     "escalate_share": sh["ESCALATE"] / sh_n if sh_n else None},
        "per_category": per_cat,
        "worst_templates": tpls[:10],
        "all_templates": tpls,
        "runtime_seconds": elapsed, "cases_per_second": total / elapsed,
        "generation_stats": gen_stats,
        "example_misses": examples,
        "misses_sample_by_category": {c: ms[:5] for c, ms in misses_by_cat.items()},
    }
    res["pytest"] = {m: run_pytest(m) for m in ["heldout", "heldout2"]}
    (ROOT / "eval/results_100k.json").write_text(json.dumps(res, indent=1))
    write_report(res)
    print(f"n={total} pass={passed/total:.4f} fb={res['benign']['false_block_rate']:.4f} "
          f"miss={res['harm']['missed_harm_rate_allow']:.4f} sh_allow={res['selfharm']['allow_share']:.4f} "
          f"{elapsed:.1f}s {total/elapsed:.0f}/s")


def run_pytest(marker):
    p = subprocess.run([sys.executable, "-m", "pytest", "-m", marker, "-q", "-p", "no:cacheprovider"],
                       cwd=ROOT, capture_output=True, text=True)
    tail = [l for l in p.stdout.splitlines() if re.search(r"passed|failed", l)]
    failed = re.findall(r"FAILED \S+\[(\w+)\]", p.stdout)
    return {"summary": tail[-1] if tail else p.stdout[-200:], "failed_ids": failed}


def pct(x):
    return f"{100*x:.2f}%"


def write_report(r):
    L = [f"# JMGL synthetic 100k evaluation (engine {r['engine_version']})", "",
         "Generated by `eval/generate.py` (seed 20260929) and scored by `eval/run_eval.py`. "
         "`eval/cases_100k.jsonl` (~20.3 MB) is gitignored; regenerate it byte-identically with "
         "`python eval/generate.py` (default seed 20260929). "
         "Rules, laws.json and engine were not modified. **Read the limitations section before citing any number.**", "",
         "## Headline", "",
         f"- Cases: {r['n']:,} (harm {r['harm']['n']:,} / benign {r['benign']['n']:,})",
         f"- Overall pass rate: **{pct(r['overall_pass_rate'])}**",
         f"- False-block rate on benign cases (BLOCK on an ALLOW case): **{pct(r['benign']['false_block_rate'])}** "
         f"(any non-ALLOW on benign: {pct(r['benign']['non_allow_rate'])})",
         f"- Missed-harm rate (harm case got ALLOW): **{pct(r['harm']['missed_harm_rate_allow'])}**",
         f"- Self-harm cases that got ALLOW: **{pct(r['selfharm']['allow_share'])}** "
         f"(ESCALATE: {pct(r['selfharm']['escalate_share'])}, n={r['selfharm']['n']:,})",
         f"- Runtime: {r['runtime_seconds']:.1f}s, {r['cases_per_second']:,.0f} cases/s (single process)", "",
         "", "## Hand-written held-out sets (pytest, reported separately)", "",
         f"- `pytest -m heldout` (original 20; H05, H09, H10 are now partly tuning data): {r['pytest']['heldout']['summary']}"
         + (f" (failed: {', '.join(r['pytest']['heldout']['failed_ids'])})" if r['pytest']['heldout']['failed_ids'] else ""),
         f"- `pytest -m heldout2` (27 cases, not used for tuning; was 26/27): {r['pytest']['heldout2']['summary']}"
         + (f" (failed: {', '.join(r['pytest']['heldout2']['failed_ids'])})" if r['pytest']['heldout2']['failed_ids'] else ""),
         "", "## Per category", "",
         "| category | expected | n | pass rate | ALLOW | BLOCK | MODIFY | ESCALATE |",
         "|---|---|---:|---:|---:|---:|---:|---:|"]
    exp_map = {"hiring": "BLOCK/MODIFY", "selfharm": "ESCALATE", "multiturn": "BLOCK/ESCALATE"}
    for c, d in r["per_category"].items():
        e = "ALLOW" if c.startswith("benign_") else exp_map.get(c, "BLOCK")
        v = d["verdicts"]
        L.append(f"| {c} | {e} | {d['n']:,} | {pct(d['pass_rate'])} | " +
                 " | ".join(str(v.get(k, 0)) for k in ["ALLOW", "BLOCK", "MODIFY", "ESCALATE"]) + " |")
    zero = [t["template_id"] for t in r["all_templates"] if t["pass_rate"] == 0]
    L += ["", "## Worst 10 templates", "",
          f"{len(zero)} templates score 0% (ties broken alphabetically below); all: {', '.join(zero)}. "
          "Full per-template table is in results_100k.json (`all_templates`).", "", "| template | category | n | pass rate |", "|---|---|---:|---:|"]
    for t in r["worst_templates"]:
        L.append(f"| {t['template_id']} | {t['category']} | {t['n']:,} | {pct(t['pass_rate'])} |")
    g = r.get("generation_stats")
    if g:
        L += ["", "## Data diversity (how much of n is real variety)", "",
              f"- Distinct base templates: {g['distinct_base_templates']} "
              f"(harm {g['harm_templates']}, benign {g['benign_templates']})",
              f"- Distinct surface strings: {g['distinct_surface_strings_total']:,} of {g['n']:,} "
              "(history+text counted together for multi-turn)", "",
              "| category | base templates | distinct surfaces |", "|---|---:|---:|"]
        for c, d in g["per_category"].items():
            L.append(f"| {c} | {d['distinct_base_templates']} | {d['distinct_surface_strings']:,} |")
    L += ["", "## Example misses", "", "| category | got (rule) | expected | text |", "|---|---|---|---|"]
    for m in r["example_misses"]:
        t = m["text"].replace("|", "/")
        if m.get("history"):
            t = "[history: " + " / ".join(m["history"]) + "] " + t
        L.append(f"| {m['category']} | {m['got']} ({m['rule_id']}) | {'/'.join(m['expected'])} | {t} |")
    L += ["", "## Limitations", "",
          "This is synthetic, templated data: ~100 hand-written base templates recombined with slot values and "
          "surface noise (prefixes, suffixes, casing, a few typos), so the 100k n greatly overstates "
          "the effective sample size; per-template pass rates are the more honest unit. The same author "
          "(an AI agent working for the project) wrote the rules, the earlier tests, and these phrasing pools; "
          "although the pools were written without opening spec/laws.json, signals.py or engine.py, shared "
          "intuitions about wording are unavoidable and likely inflate pass rates. Labels are the generator "
          "author's intended labels, not independent human annotations, and some borderline templates may be "
          "mislabeled. English only; no real user traffic, no adversarial paraphrasing by a third party, and "
          "no measurement of the quality of the responses/resources, only the decision label. These numbers "
          "should not be read as a real-world accuracy estimate.", ""]
    (ROOT / "eval/REPORT.md").write_text("\n".join(L))


if __name__ == "__main__":
    main()
