# JMGL two-stage gate on the synthetic 100k set (judge backend: `null`)

Engine jmgl-0.1.1, merge jmgl-merge-0.2.0. Same cases as `REPORT.md` (regenerate with `python eval/generate.py`). Public verdicts: APPROVE / REVIEW / REJECT. See `docs/HYBRID_SPEC.md`.

**This is the fail-closed baseline, not a before/after comparison.** NullJudge never answers, so every case goes through the fail-closed branch: rule ALLOW becomes REVIEW, and any rule flag becomes REJECT. No case can be APPROVEd. Real before/after numbers need a real model judge, which is not connected yet.

## Headline

- Cases: 100,000 (harm 49,830 / benign 50,170); judge_status: {'absent': 100000}
- Missed harm (harm case APPROVEd): **0.00%** (harm REVIEW 65.02%, REJECT 34.98%)
- Benign APPROVE rate: **0.00%** (benign REVIEW 88.10%, REJECT 11.90%)
- REVIEW volume: **76,600 cases (76.60% of all)**
- Self-harm: APPROVE 0.00%, REJECT with 988 resources 44.17% (n=9,133)
- Runtime: 39.5s, 2,530 cases/s

## Per category

| category | n | APPROVE | REVIEW | REJECT | decided_by |
|---|---:|---:|---:|---:|---|
| authclaim | 3,748 | 0 | 1582 | 2166 | fail_closed:3748 |
| benign_auth | 2,593 | 0 | 2593 | 0 | fail_closed:2593 |
| benign_crypto | 3,863 | 0 | 3863 | 0 | fail_closed:3863 |
| benign_elder | 5,164 | 0 | 5164 | 0 | fail_closed:5164 |
| benign_fiction | 5,136 | 0 | 5136 | 0 | fail_closed:5136 |
| benign_hiring | 5,127 | 0 | 3888 | 1239 | fail_closed:5127 |
| benign_locate | 6,453 | 0 | 5695 | 758 | fail_closed:6453 |
| benign_multi | 2,532 | 0 | 2532 | 0 | fail_closed:2532 |
| benign_phish | 6,396 | 0 | 2423 | 3973 | fail_closed:6396 |
| benign_secure | 6,392 | 0 | 6392 | 0 | fail_closed:6392 |
| benign_vent | 6,514 | 0 | 6514 | 0 | fail_closed:6514 |
| creds | 4,499 | 0 | 3713 | 786 | fail_closed:4499 |
| elderfin | 4,711 | 0 | 4257 | 454 | fail_closed:4711 |
| hiring | 4,659 | 0 | 3175 | 1484 | fail_closed:4659 |
| jailbreak | 4,631 | 0 | 3508 | 1123 | fail_closed:4631 |
| multiturn | 3,899 | 0 | 2800 | 1099 | fail_closed:3899 |
| phishing | 5,453 | 0 | 2593 | 2860 | fail_closed:5453 |
| pumpdump | 4,604 | 0 | 3859 | 745 | fail_closed:4604 |
| selfharm | 9,133 | 0 | 5099 | 4034 | crisis:rule:4034, fail_closed:5099 |
| stalking | 4,493 | 0 | 1814 | 2679 | fail_closed:4493 |

## Caveats

Same synthetic, templated, single-author data as `REPORT.md`, with the same limitations. Under NullJudge, REVIEW just means "the rule stage saw nothing and no judge answered"; it is a queue for a human or a real judge, not a detection. Harm cases landing in REVIEW are not caught; they are only kept from being auto-approved.
