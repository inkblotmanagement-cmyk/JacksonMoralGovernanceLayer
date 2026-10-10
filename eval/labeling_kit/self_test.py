"""End-to-end smoke test for the kit's scoring pipeline, using FABRICATED labels.

It does NOT produce real results. It creates two mock 'filled' sheets from the
answer key (labeler B is given ~12% random disagreement and a few blanks to mimic
real labelers), then runs agreement.py and score_vs_human.py so we can confirm the
scripts work before any human touches them. Outputs go to _selftest/ and are safe
to delete.

Usage: python eval/labeling_kit/self_test.py
"""
from __future__ import annotations
import csv, random, subprocess, sys
from pathlib import Path

KIT = Path(__file__).resolve().parent
ST = KIT / "_selftest"
LABELS = ["Safe - just help", "Fix or limit it first", "Refuse - it's harmful", "Get a human / crisis help"]
DEC2LAB = {"ALLOW": LABELS[0], "MODIFY": LABELS[1], "BLOCK": LABELS[2], "ESCALATE": LABELS[3]}


def main():
    ST.mkdir(exist_ok=True)
    rows = list(csv.DictReader((KIT / "_answer_key.csv").open()))
    rng = random.Random(1)
    a_path, b_path = ST / "mock_A.csv", ST / "mock_B.csv"
    for path, noise in [(a_path, 0.0), (b_path, 0.12)]:
        with path.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["item_id", "request", "label (pick one)", "notes (optional)"])
            for r in rows:
                lab = DEC2LAB.get(r["decision_expected_synthetic"], LABELS[0])
                if rng.random() < noise:
                    lab = rng.choice(LABELS)          # simulate a disagreement
                if rng.random() < 0.02:
                    lab = ""                           # simulate a blank
                w.writerow([r["item_id"], r["request"], lab, ""])
    gold = ST / "mock_gold.csv"
    print("=== agreement.py (fabricated labels) ===")
    subprocess.run([sys.executable, str(KIT / "agreement.py"), str(a_path), str(b_path),
                    "--out", str(gold)], check=True)
    print("\n=== score_vs_human.py (fabricated gold) ===")
    for sysn in ("grace", "ensemble"):
        subprocess.run([sys.executable, str(KIT / "score_vs_human.py"),
                        "--gold", str(gold), "--system", sysn], check=True)
    print("\nSelf-test complete. _selftest/ is fabricated data; delete it any time.")


if __name__ == "__main__":
    main()
