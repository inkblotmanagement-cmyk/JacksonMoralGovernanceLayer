# JMGL v0.4 accuracy report — rules + learned classifier ensemble

**Goal:** raise JMGL's *predictive accuracy* (correct ALLOW / BLOCK / MODIFY /
ESCALATE vs. ground-truth label) to **≥ 85% on held-out test data, measured
honestly.** A case is **correct** when the decision is in its accepted `expected`
set (the generator allows two labels for `hiring` = BLOCK|MODIFY and `multiturn`
= BLOCK|ESCALATE).

## Headline

| set | n | rule-only (v0.3) | **ensemble (v0.4)** | harm-miss | benign false-positive |
|---|---|---|---|---|---|
| **held-out test, template-disjoint** | 21,722 | 52.7% | **88.1%** | 1.8% | 28.3% |
| held-out test, random split | 16,331 | 57.3% | 89.4% | 1.7% | 21.6% |
| **fresh paraphrase set** (hand-written, trigger words avoided) | 66 | 47.0% | **89.4%** | 2.4% | 24.0% |
| fresh hand-written set (v0.3, 46) | 46 | 43.5% | 73.9% | 37.0% | 0.0% |
| held-out #1 (20) | 20 | 100% | 95.0% | – | – |
| held-out #2 (27) | 27 | 96.3% | 92.6% | – | – |
| post-hoc probe (10) | 10 | 40.0% | 70.0% | – | – |

**The target is met on the honest headline sets:** 88.1% on the template-disjoint
held-out split (no phrasing template shared with training) and 89.4% on a fresh,
differently-worded hand-written set. For comparison, the pre-existing baselines
were ~62% (rules only) and ~76% (rules + local Qwen-1.5B judge) on the full 100k /
a 5k sample. **Latency: ~6 ms per decision** (ensemble, CPU) vs ~0.5 ms rule-only
and ~1,900 ms for the Qwen judge.

harm-miss = a harm case decided ALLOW. benign false-positive = a benign case
decided anything other than ALLOW. (For the small external sets the harm/benign
split can't be computed reliably from their labels, so only accuracy is shown.)

## What changed

1. **Learned category classifier** (`src/jmgl/classifier.py`): sentence
   embeddings (`BAAI/bge-small-en-v1.5`, 384-d, Apache-2.0, ~130 MB, CPU via
   fastembed/onnxruntime) **concatenated with the engine's own regex signal
   features plus richer mitigation/harm cues** (`src/jmgl/features.py`, 33
   features: educational/fairness/own-account/consent/fiction framing and
   covert/impersonation cues), standardized, fed to a multinomial logistic
   regression. It predicts a scenario *category*, mapped to a four-way decision.
   Inference is numpy-only; weights live in `eval/model/clf.npz` (40 KB, committed).
   The embedding model downloads to the HuggingFace cache on first use and is
   never committed (same policy as the Qwen judge).
2. **Fail-closed ensemble merge** (`src/jmgl/ensemble.py`, policy calibrated on
   the dev split only):
   - self-harm / crisis always wins → ESCALATE with resources;
   - a benign look-alike is rescued to ALLOW only when the classifier alone flags
     harm, the rules did not, a mitigation cue is present and no covert-harm cue is;
   - otherwise **any** harm vote wins (fail-closed): this is what catches the
     paraphrased harm the keyword rules miss (rule-only harm-miss ~65–68%).
   - If the classifier or its model files are unavailable, it falls back to the
     rule engine alone (never crashes).
3. New CLI flag `python -m jmgl --ensemble "..."` and `evaluate_action_ensemble`.

## Method (honesty protocol)

- **Split BEFORE tuning.** `eval/build_splits.py` regenerates two independent
  held-out views from the seeded 100k set, deterministically (seed 20261007),
  after removing exact-duplicate surface strings (81,655 unique of 100,000):
  - **template-disjoint** (the honest headline): every base phrasing template is
    assigned to exactly one of train / dev / test, so **no template seen in
    training appears in dev or test.** This measures generalization to new
    phrasings of a category, not template memorization. (train 44,910 / dev
    15,023 / test 21,722.) A hard assert verifies no template leaks across splits.
  - **random split** (easy, shown only for the overfit gap): templates are shared
    across splits.
- **Train on train only** (`eval/train_classifier.py`); the LR regularization C
  is selected on **dev only**; test is never read during training.
- **Merge policy and thresholds calibrated on dev only** (`eval/calibrate.py`).
- **Fresh generalization set written separately** (`tests/fresh_paraphrase.json`,
  66 cases): hand-written paraphrases that deliberately avoid obvious trigger
  words (no "phishing", "spoof", "stalk", "kill myself", …). Never used to tune
  anything. The older `tests/fresh_handwritten.json` (46) is also reported.
- **Deduplication** removes near-identical templated strings so they can't cross
  splits.

## Per-category accuracy (ensemble)

**Template-disjoint TEST (n=21,722, 88.1%).** Harm categories are near-perfect;
the misses are benign look-alikes whose single held-out phrasing collides with a
harm category:

```
HARM:   authclaim 1.00  creds 1.00  elderfin 0.88  hiring 0.97  jailbreak 1.00
        multiturn 1.00  phishing 1.00  pumpdump 1.00  selfharm 1.00  stalking 1.00
BENIGN: benign_crypto 1.00  benign_elder 1.00  benign_fiction 1.00
        benign_hiring 1.00  benign_vent 1.00  benign_locate 0.86  benign_secure 0.72
        benign_phish 0.00  benign_auth 0.00  benign_multi 0.00
```

Confusion (rows = expected primary label, cols = decision):
```
ALLOW    -> ALLOW 5959, BLOCK 2280, ESCALATE 69
BLOCK    -> BLOCK 10349, MODIFY 1478, ALLOW 238
ESCALATE -> ESCALATE 1349
```

**Fresh paraphrase (n=66, 89.4%).** All 10 harm scenarios caught, self-harm 6/6;
remaining misses are benign look-alikes (benign_phish 1/3, benign_hiring 1/2).

## Honest caveats and limitations

- **Benign over-blocking is the real remaining weakness.** The ensemble decides
  ~28% of benign cases as something other than ALLOW on the synthetic test (24%
  on the fresh set). This is largely three benign sub-types whose single held-out
  phrasing the classifier confuses with a harm category: scam-awareness/training
  (`benign_phish`→phishing), "as the owner, do this benign task" (`benign_auth`→
  authclaim, which the rule stage itself also blocks via JL-09), and innocent
  "combine the above" (`benign_multi`→multiturn). Many of these land on MODIFY/
  ESCALATE (human review) rather than a hard block, but they are still false
  alarms a user would feel. Rule-only over-blocks far less (~6–14%) but misses
  ~65% of harm; the ensemble trades some benign friction for catching harm.
- **The fresh hand-written set is only 73.9%.** The subtle, metaphorical
  self-harm and fake-consent cases ("I've made peace with checking out",
  "she agreed") are still missed ~37% of the time. The headline numbers should
  not be read as "works on every real phrasing."
- **All data was authored by the same AI agent** who wrote the rules, the
  generator, the classifier and every test set, including the fresh ones. These
  are **not independent human annotations.** Shared blind spots are likely and
  the fresh set was written by the same hand that could anticipate the model.
- **Synthetic, templated, English-only data** (104 base templates). The
  template-disjoint split removes template memorization but not author bias.
- **No calibration of resource quality** — only the decision label is scored, not
  whether the self-harm resources or the modification advice are actually good.
- **What would raise this further / make it trustworthy:** real labeled requests
  from pilots (not synthetic), independent human annotation, more diverse benign
  look-alikes in training to cut false positives, and a larger embedding or a
  judge model (the box has no GPU and ~2 GB free, so model size was capped).

## Reproduce

```
python eval/generate.py --n 100000          # regenerate seeded cases (gitignored)
python eval/build_splits.py                  # train/dev/test (gitignored, deterministic)
python eval/train_classifier.py              # trains eval/model/clf.npz (committed)
python eval/calibrate.py                     # dev-only merge calibration
python eval/run_accuracy.py                  # -> eval/accuracy_results.json
pip install scikit-learn fastembed           # extra deps for training/inference
```
