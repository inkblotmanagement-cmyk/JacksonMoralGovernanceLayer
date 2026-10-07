# Grace Force report — a measurable score with a 0.7 pass line + rewrite path

**What this is.** Grace Force is a 0..1 score toward the Grace Physics goal of
aligning capable AI with human flourishing. It is a **transparent, configurable
heuristic composite**, not an independent measurement of real-world benefit, and
not "as reliable as gravity." Weights and the 0.7 line live in
[`spec/grace_force.json`](../spec/grace_force.json).

Grace Force = weighted sum of four components (defaults, weights sum to 1.0):

| component | weight | how it is estimated | strength |
|---|---|---|---|
| harm_avoided | 0.40 | grounded in the JMGL law verdict (no JL-00..JL-10 violation), minus a small classifier-harm caution; **squared penalty** for irreversible categories | strong |
| human_benefit | 0.25 | benign vs harm category + benefit-word cues | proxy (weak) |
| long_term_flourishing | 0.20 | skills/income/well-being word cues + category | proxy (weak) |
| confidence | 0.15 | classifier confidence; below 0.45 also **routes to a person** | medium |

**Decision:** self-harm → ESCALATE (resources); a **hard law BLOCK → BLOCK,
never rewritten**; a clear laundering/harm cue → ESCALATE; score ≥ 0.7 → ALLOW;
score < 0.7 → rewrite path, returning the rewrite only if it reaches ≥ 0.7 **and**
still passes the laws **and** stays below the harm cap, else ESCALATE.

## Does 0.7 separate labeled-safe from labeled-harmful? (held-out, honest)

Decision = correct if in the case's accepted label set. Grace was tuned only on
the dev split; the constants were never fit to these test sets.

| set | n | accuracy @0.7 | harm-miss | benign over-flag | latency |
|---|---|---|---|---|---|
| template-disjoint held-out test (sample) | 3,000 | 68.3% | **0.0%** | 62.6% | ~35 ms |
| fresh paraphrase (trigger words avoided) | 66 | 83.3% | **0.0%** | 28.0% | ~39 ms |
| fresh hand-written (harder) | 46 | 60.9% | 21.7% | 0.0% | ~24 ms |

**Decisions at 0.7 on the 3,000-case test:** BLOCK 1,746 · ESCALATE 823 · ALLOW
429 · MODIFY 2. The benign "over-flag" is **mostly ESCALATE (routed to a human
reviewer), not a hard block.**

### Threshold sweep (score-only separation: harm-miss / benign-over-flag)

Template-disjoint test:
```
t=0.50 0.02/0.41   t=0.55 0.00/0.60   t=0.60 0.00/0.60   t=0.65 0.00/0.60
t=0.70 0.00/0.62   t=0.75 0.00/0.68   t=0.80 0.00/0.89   t=0.85 0.00/1.00
```
Fresh paraphrase:
```
t=0.50 0.02/0.28   t=0.60 0.02/0.28   t=0.70 0.00/0.28   t=0.80 0.00/0.48
```
Fresh hand-written (n=46, noisy):
```
t=0.50 0.33/0.00   t=0.70 0.24/0.00   t=0.75 0.15/0.00   t=0.80 0.00/0.00
```

**Reading of 0.7.** On the synthetic and fresh-paraphrase data, **harm is almost
perfectly separated** — essentially no harmful action scores ≥ 0.55, so 0.7 gives
0% harm-miss. The cost is **benign over-flagging (~28% on natural paraphrases,
~63% on the hardest unseen-template set).** Crucially, **lowering the threshold
barely helps the benign rate** (it is ~0.60 from 0.55 to 0.70 on the hard set),
because the over-flagging is driven by the underlying classifier confusing benign
look-alikes (scam-awareness, fair hiring, "as the owner do X", innocent "combine
the above") on unseen templates — not by where the line sits. So **0.7 is a safe,
conservative line** for harm; it is not the knob that fixes benign friction.
On the harder hand-written set, subtle/metaphorical self-harm needs ~0.8 to be
caught, mirroring the known weakness of the small classifier.

## Rewrite path

| set | below-0.7 & not hard-block | benign rewritten to pass | harmful wrongly passed by rewrite |
|---|---|---|---|
| template-disjoint test | 614 | 2 | **0** |
| fresh paraphrase | 6 | 0 | **0** |
| fresh hand-written | 8 | 0 | **0** |

- **Harmful actions laundered through a rewrite: 0** on every set. A harmful goal
  cannot be reworded into a pass: additive safeguards (consent / disclosure /
  human-review / scope-down) keep the harmful core, so the re-score still fails;
  only the **transformative** fair-hiring rewrite (which actually removes the
  discriminatory criterion) can pass, and it is re-checked against the laws.
- **Benign rescue is rare (2/614).** Most below-threshold benign cases are
  classifier-confused look-alikes with high harm probability, which are (by the
  anti-laundering guard) not eligible for additive rewrites, so they ESCALATE to
  a human instead. The rewrite path is therefore a narrow, safe tool, not a
  general benign-recovery mechanism today.

## Red-team: laundering a harmful goal through benign wording

`tests/grace_redteam.json` — 15 harmful requests dressed in "for security
awareness", "for her safety", "with consent", "fair hiring", "I authorize you":

**Laundered through: 0 / 15.** Decisions: 13 BLOCK, 2 ESCALATE, 0 ALLOW, 0
passing rewrite. One case ("fair hiring … quietly screen out … zip codes")
initially passed and exposed two bugs (a 3rd-person "filters out" the exclusion
regex missed, and proxy terms like "the east side" that were not listed); both
were fixed, and a Grace-layer **hard-harm override** now routes covert,
impersonation-for-credentials, and discriminatory-proxy-exclusion requests to a
human even when the score would otherwise pass.

## Honest caveats

- **Benign over-flagging is high** (~63% on the hardest set, ~28% on natural
  paraphrases), mostly as ESCALATE/REVIEW. This inherits the small classifier's
  benign/harm confusion and is made stricter by the 0.7 line. As a pure accuracy
  layer Grace (68% at 0.7) is **lower than the v0.4 ensemble (88%)**; Grace is a
  safety-first gate, not a replacement for the ensemble's routine ALLOW/BLOCK.
- **human_benefit and long_term_flourishing are lexical proxies** — the weakest
  parts of the score. Grace Force does not actually measure benefit; it estimates
  it from words and categories. Real benefit/flourishing need real outcome data.
- **Subtle self-harm and fake-consent still slip** on the hardest hand-written
  set (harm-miss 22% at 0.7), same blind spot as the classifier.
- **All data is AI-generated by the same author** as the rules/score/tests
  (including the red-team set), so laundering coverage is a lower bound; a human
  red-team would likely find more. This needs **independent, human-labeled
  evaluation** before any strong claim.
- The irreversible-category list, weights, thresholds and proxy vocabularies are
  drafts in `spec/grace_force.json` and need Terrance's review.

## Reproduce

```
python eval/build_splits.py            # deterministic splits (gitignored)
python eval/train_classifier.py        # classifier weights (committed, 40 KB)
python eval/run_grace.py               # -> eval/grace_results.json
pip install numpy scikit-learn fastembed
```
