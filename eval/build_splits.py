"""Build train/dev/test splits for the JMGL category classifier.

Two independent held-out views are produced so accuracy can be reported honestly:

1. TEMPLATE-DISJOINT split (the honest headline). Each base template id is
   assigned to exactly one of train / dev / test, so no phrasing template seen
   in training appears in dev or test. This measures generalization to new
   phrasings of the same scenario category, not memorization of templates.

2. RANDOM split (dedup). A plain shuffled split over deduplicated surface
   strings. Templates are shared across splits, so this is the EASY view and is
   reported only to show the overfit gap vs. the template-disjoint view.

Exact-duplicate surface strings (the full text, plus history for multi-turn) are
removed first and never allowed to cross splits. Deterministic (seed 20261007).

Usage: python eval/build_splits.py
Writes eval/splits/{train,dev,test,random_train,random_dev,random_test}.jsonl
and eval/splits/split_manifest.json (template assignments + counts).
"""
from __future__ import annotations
import json, random
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CASES = ROOT / "eval/cases_100k.jsonl"
OUT = ROOT / "eval/splits"
SEED = 20261007


def surface_key(c):
    if c.get("history"):
        return " || ".join(c["history"] + [c["text"]])
    return c["text"]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)
    cases = [json.loads(l) for l in CASES.open()]

    # 1) dedup exact surface strings (keep first occurrence)
    seen = set()
    deduped = []
    for c in cases:
        k = surface_key(c)
        if k in seen:
            continue
        seen.add(k)
        deduped.append(c)
    print(f"{len(cases)} cases -> {len(deduped)} after exact-dedup")

    # 2) template-disjoint assignment, stratified within each category
    tpls_by_cat = defaultdict(set)
    for c in deduped:
        tpls_by_cat[c["category"]].add(c["template_id"])
    tpl_split = {}  # template_id -> 'train'|'dev'|'test'
    for cat, tpls in sorted(tpls_by_cat.items()):
        tl = sorted(tpls)
        rng.shuffle(tl)
        n = len(tl)
        if n == 1:
            assign = ["train"]
        elif n == 2:
            assign = ["train", "test"]
        elif n == 3:
            assign = ["train", "train", "test"]
        else:
            n_test = max(1, round(n * 0.25))
            n_dev = max(1, round(n * 0.15))
            n_train = n - n_test - n_dev
            if n_train < 1:
                n_train, n_dev = 1, n - n_test - 1
            assign = ["train"] * n_train + ["dev"] * n_dev + ["test"] * n_test
        for t, a in zip(tl, assign):
            tpl_split[t] = a

    buckets = defaultdict(list)
    for c in deduped:
        buckets[tpl_split[c["template_id"]]].append(c)
    for name in ("train", "dev", "test"):
        rng.shuffle(buckets[name])
        (OUT / f"{name}.jsonl").write_text("".join(json.dumps(c) + "\n" for c in buckets[name]))

    # 3) random split (dedup), templates shared
    rand = deduped[:]
    rng.shuffle(rand)
    n = len(rand)
    r_test = rand[: int(n * 0.2)]
    r_dev = rand[int(n * 0.2): int(n * 0.3)]
    r_train = rand[int(n * 0.3):]
    for name, data in (("random_train", r_train), ("random_dev", r_dev), ("random_test", r_test)):
        (OUT / f"{name}.jsonl").write_text("".join(json.dumps(c) + "\n" for c in data))

    manifest = {
        "seed": SEED,
        "n_cases": len(cases),
        "n_deduped": len(deduped),
        "template_disjoint": {k: len(buckets[k]) for k in ("train", "dev", "test")},
        "template_assignment": tpl_split,
        "random": {"train": len(r_train), "dev": len(r_dev), "test": len(r_test)},
    }
    (OUT / "split_manifest.json").write_text(json.dumps(manifest, indent=1))
    print("template-disjoint:", manifest["template_disjoint"])
    print("random:", manifest["random"])
    # sanity: no template crosses template-disjoint splits
    cross = defaultdict(set)
    for name in ("train", "dev", "test"):
        for c in buckets[name]:
            cross[c["template_id"]].add(name)
    assert all(len(v) == 1 for v in cross.values()), "template leakage!"
    print("OK: no template leakage across template-disjoint splits")


if __name__ == "__main__":
    main()
