# JMGL human labeling kit

Two non-technical staff independently label ~300 real requests so we can check
JMGL against **human** judgment — every other eval set in this repo was written by
an AI, so this is our one human-grounded measure.

## Why
- Independent ground truth (not the system's authors, not AI-generated).
- Measures inter-rater agreement (do two reasonable people even agree?).
- Scores JMGL against the human consensus, with harm-miss and over-flag reported
  separately.

## Files
| File | For whom | What |
|---|---|---|
| `GUIDE.md` | **labelers** | One-page plain-language instructions + examples. Read first. |
| `labeler_A.xlsx`, `labeler_B.xlsx` | **labelers** | Each person fills their own. 4 session tabs (~75 items each, <1 hour), dropdown label + notes, content warning on the first tab. |
| `labeler_A_session*.csv`, `labeler_B_session*.csv` | labelers | Same content as CSV, if someone prefers it over Excel. |
| `_answer_key.csv` | **scorers only — do NOT send to labelers** | item → request, kind, category, source, and the synthetic expected decision. |
| `common.py` | scripts | Shared reader (handles xlsx/csv, label normalization). |
| `agreement.py` | scorers | Inter-rater agreement + consensus `human_gold.csv`. |
| `score_vs_human.py` | scorers | Scores the system against `human_gold.csv`. |
| `self_test.py` | devs | Smoke-tests the pipeline with FABRICATED labels (writes `_selftest/`). |
| `build_kit.py` | devs | Regenerates the sample + sheets (deterministic seed). |

## Content warning
Some items describe self-harm, scams, and abuse. The warning is on the sheets and
in `GUIDE.md`. US crisis support: call/text **988**.

## Labels (plain → JMGL decision)
`Safe - just help`→ALLOW · `Fix or limit it first`→MODIFY · `Refuse - it's harmful`→BLOCK · `Get a human / crisis help`→ESCALATE

## Workflow
1. Send each labeler **only**: `GUIDE.md` + their own `labeler_X.xlsx` (or CSVs).
   Do **not** send the answer key. They work **alone**.
2. Collect the two filled files (e.g. `labeler_A_FILLED.xlsx`, `labeler_B_FILLED.xlsx`).
3. Agreement + consensus:
   ```
   python eval/labeling_kit/agreement.py labeler_A_FILLED.xlsx labeler_B_FILLED.xlsx
   ```
   (CSV users: pass the four comma-joined, e.g. `a1.csv,a2.csv,a3.csv,a4.csv`.)
   This prints % agreement + Cohen's kappa + the disagreements, and writes
   `human_gold.csv` (the rows they agree on).
4. Score the system against the humans:
   ```
   python eval/labeling_kit/score_vs_human.py --system grace      # or ensemble / rules
   ```
5. (Optional) adjudicate the disagreement list together and add those rows to
   `human_gold.csv` by hand before re-scoring.

## Notes on honesty
- Labelers never see model output or the "expected" column, to avoid anchoring.
- `score_vs_human.py` also reports whether the AI-written `expected` labels agree
  with the humans — a low number there would mean our synthetic ground truth is
  off, which you'd want to know.
- 300 items can't certify safety; it's a reality check on the synthetic numbers.
