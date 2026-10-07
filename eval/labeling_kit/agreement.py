"""Inter-rater agreement between the two labelers, and a consensus 'human gold'
label where they agree.

Usage:
  python eval/labeling_kit/agreement.py LABELER_A_FILLED LABELER_B_FILLED \
      [--out human_gold.csv]

Each argument is a filled .xlsx (all sessions) OR you can pass several .csv files
per labeler separated by commas, e.g. a1.csv,a2.csv,a3.csv,a4.csv.

Reports: overlap count, raw percent agreement, Cohen's kappa, a per-label
breakdown, and the list of disagreements. Writes human_gold.csv for the rows the
two labelers agree on (that file is the human ground truth used by
score_vs_human.py).
"""
from __future__ import annotations
import argparse, csv
from collections import Counter
from pathlib import Path
from common import read_filled, LABEL_TO_DECISION, LABELS, KIT


def read_multi(arg):
    merged = {}
    for part in arg.split(","):
        merged.update(read_filled(part.strip()))
    return merged


def cohen_kappa(pairs, cats):
    n = len(pairs)
    if n == 0:
        return float("nan")
    po = sum(a == b for a, b in pairs) / n
    ca = Counter(a for a, _ in pairs); cb = Counter(b for _, b in pairs)
    pe = sum((ca[c] / n) * (cb[c] / n) for c in cats)
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("labeler_a"); ap.add_argument("labeler_b")
    ap.add_argument("--out", default=str(KIT / "human_gold.csv"))
    a = ap.parse_args()
    A, B = read_multi(a.labeler_a), read_multi(a.labeler_b)
    key = read_answer_key_text()

    common = sorted(set(A) & set(B))
    both_labeled = [i for i in common if A[i]["label"] and B[i]["label"]]
    pairs = [(A[i]["label"], B[i]["label"]) for i in both_labeled]
    valid_labels = set(LABELS)
    unknown = sorted({l for p in pairs for l in p if l not in valid_labels})

    agree = [i for i in both_labeled if A[i]["label"] == B[i]["label"]]
    disagree = [i for i in both_labeled if A[i]["label"] != B[i]["label"]]
    pct = len(agree) / len(both_labeled) if both_labeled else float("nan")
    kappa = cohen_kappa(pairs, LABELS)

    print(f"Labeler A rows: {len(A)}   Labeler B rows: {len(B)}")
    print(f"Both labeled the same item: {len(both_labeled)}")
    miss_a = [i for i in common if not A[i]['label']]
    miss_b = [i for i in common if not B[i]['label']]
    if miss_a or miss_b:
        print(f"  (blank labels — A: {len(miss_a)}, B: {len(miss_b)})")
    if unknown:
        print(f"  WARNING unrecognized label values: {unknown}")
    print(f"Raw agreement: {pct:.1%}  ({len(agree)}/{len(both_labeled)})")
    print(f"Cohen's kappa: {kappa:.3f}  "
          f"({'slight' if kappa<0.2 else 'fair' if kappa<0.4 else 'moderate' if kappa<0.6 else 'substantial' if kappa<0.8 else 'almost perfect'})")
    print("\nPer-label agreement (where at least one picked it):")
    for lab in LABELS:
        rel = [i for i in both_labeled if lab in (A[i]["label"], B[i]["label"])]
        both = [i for i in rel if A[i]["label"] == lab and B[i]["label"] == lab]
        print(f"  {lab:28s} A∪B={len(rel):3d}  both={len(both):3d}")

    if disagree:
        print(f"\nDisagreements ({len(disagree)}) — review these together:")
        for i in disagree:
            txt = key.get(i, {}).get("request", "")[:70]
            print(f"  {i}: A={A[i]['label']!r:30s} B={B[i]['label']!r:30s} | {txt}")

    with open(a.out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["item_id", "request", "human_label", "human_decision"])
        for i in agree:
            lab = A[i]["label"]
            w.writerow([i, key.get(i, {}).get("request", ""), lab, LABEL_TO_DECISION.get(lab, "")])
    print(f"\nWrote {len(agree)} consensus rows -> {a.out}")
    print("Next: python eval/labeling_kit/score_vs_human.py")


def read_answer_key_text():
    out = {}
    p = KIT / "_answer_key.csv"
    if p.exists():
        with p.open() as f:
            for row in csv.DictReader(f):
                out[row["item_id"]] = row
    return out


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    main()
