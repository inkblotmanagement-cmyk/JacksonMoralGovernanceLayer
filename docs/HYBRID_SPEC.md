# JMGL two-stage fail-closed gate (v0.2 design)

> **JMGL is a policy engine for AI workflows. The pattern layer is fast and incomplete. Harm categories require a model judge plus fail-closed merge.**

Why: on the synthetic 100k set (`eval/REPORT.md`) the regex rule stage alone let **65.02%** of harm cases through as ALLOW, including **55.83%** of soft-language self-harm cases, and it false-blocked 9.43% of benign look-alikes. Pattern rules can't be the only line of defense for harm categories.

## Stages

1. **Rule stage**: the existing, unmodified regex engine (`jmgl.evaluate_action`, laws JL-00…JL-10). It's deterministic, offline and fast (about 2.6k cases/s), but incomplete.
2. **Judge stage**: a pluggable model judge (`jmgl.judge`). It gets the request, the history and the context flags, and must return one JSON object that validates against `spec/judge_schema.json`.
3. **Merge**: `jmgl.merge.merge(rule_verdict, judge_verdict, judge_error, context)` combines the two. Missing or unusable judge output always fails closed. Every merged decision is written to the audit log.

`jmgl.merge.gate(request, context, judge, audit_path=...)` runs all three stages.

## Judge output schema (`spec/judge_schema.json`)

```json
{"decision": "APPROVE|REVIEW|REJECT",
 "category": "self_harm|suicide|stalking_surveillance|credential_theft|elder_financial_abuse|investment_hype|jailbreak|phishing_impersonation|discriminatory_hiring|benign_training|benign_social|benign_other",
 "rationale_short": "string, <= 200 chars",
 "confidence": 0.0}
```

All four keys are required, `additionalProperties: false`, and confidence must be between 0 and 1. Validation uses `jsonschema` (Draft 2020-12) when it is installed, and a hand validator with the same rules otherwise (a test checks that the two agree). A judge reply that isn't JSON, has extra or missing keys, or has an out-of-enum value counts as `invalid`.

## Public verdicts and rule-stage mapping

| engine decision | public verdict | notes |
|---|---|---|
| ALLOW | APPROVE | |
| MODIFY | REVIEW | `suggested_modification` (the fair alternative) is kept |
| BLOCK | REJECT | |
| ESCALATE | REJECT + crisis resources | 988 Suicide & Crisis Lifeline, 911, findahelpline.com. The request is never completed. |

## Merge rules (applied in order)

1. **Crisis first.** If the rule stage ESCALATEs (JL-08), or a schema-valid judge output has category `self_harm` or `suicide` (whatever its decision), the result is **REJECT** with the 988 resources attached (`crisis=true`). Context flags never apply here.
2. **Fail closed.** If `judge_status` is `absent`, `error` (including timeout) or `invalid`, the result is never APPROVE. It is **REVIEW** if the rule stage said ALLOW, and **REJECT** if the rule stage flagged anything (BLOCK or MODIFY).
3. **A judge REJECT means REJECT.**
4. **A rule REJECT means REJECT**, with one exception, the *flag lift*:
   - `training=true`, rule `JL-01` (phishing), and the judge independently returns `APPROVE` + `benign_training`: the result is **APPROVE**.
   - `consensual_share=true`, rule `JL-04` (locate/track), and the judge independently returns `APPROVE` + `benign_social`: the result is **APPROVE**.
5. **APPROVE only if both approve.** Anything else is REVIEW. A judge `APPROVE` with a non-benign category contradicts itself, so it is treated as REVIEW.

## Truth table

`judge ok` means the judge output is present and schema-valid. The "crisis" rows take precedence over everything else.

| rule stage (public) | judge | flags | final | decided_by |
|---|---|---|---|---|
| ESCALATE→REJECT (JL-08) | anything (absent/invalid/APPROVE/…) | any | **REJECT + 988** | crisis:rule / crisis |
| any | ok, category self_harm / suicide (any decision) | any | **REJECT + 988** | crisis:judge / crisis |
| APPROVE | absent / error / timeout / invalid | any | **REVIEW** | fail_closed |
| REVIEW (MODIFY) | absent / error / timeout / invalid | any | **REJECT** | fail_closed |
| REJECT (BLOCK) | absent / error / timeout / invalid | any | **REJECT** | fail_closed |
| any | ok, REJECT | any | **REJECT** | judge / both |
| REJECT | ok, APPROVE (benign_training), rule JL-01 | training | **APPROVE** | flag_lift |
| REJECT | ok, APPROVE (benign_social), rule JL-04 | consensual_share | **APPROVE** | flag_lift |
| REJECT | ok, APPROVE / REVIEW (any other case) | any | **REJECT** | rule |
| APPROVE | ok, APPROVE with a benign_* category | any | **APPROVE** | both |
| APPROVE | ok, APPROVE with a harm category | any | **REVIEW** | judge |
| APPROVE | ok, REVIEW | any | **REVIEW** | judge |
| REVIEW (MODIFY) | ok, APPROVE / REVIEW | any | **REVIEW** (alternative kept) | rule / both |

## Context flags

`training` and `consensual_share` are caller-supplied **claims**, not proof. They are:
- passed to the judge (in the prompt, marked as claims to be checked against the text itself);
- recorded in every audit record (`flags`, `flag_lift`);
- only able to lift a **rule-stage** false alarm on JL-01 or JL-04, and only when the judge independently returns APPROVE with the matching benign category;
- never able to override a judge REJECT, never used when the judge is absent or invalid, and never applied to self-harm or suicide.

## Audit record (one JSONL line per merged decision)

`timestamp, input_sha256, stage="merged", decision, decided_by, reason, rule_decision, rule_id, judge_status (ok|error|invalid|absent), judge_backend, judge_decision, judge_category, judge_confidence, judge_error, flags, flag_lift, crisis, engine_version, merge_version, laws_sha256, judge_schema_sha256`. The raw input is hashed, not stored.

## Judge backends (`src/jmgl/judge.py`)

- `NullJudge`: always absent. This is the default and exercises the fail-closed path.
- `FakeJudge`: scripted outputs and exceptions, for tests.
- `OpenAICompatJudge`: optional. It POSTs to `$JMGL_JUDGE_BASE_URL/chat/completions` (default `https://api.openai.com/v1`) using `$JMGL_JUDGE_API_KEY` and `$JMGL_JUDGE_MODEL`, with temperature 0, JSON mode and a 10 s timeout. It uses the stdlib only. If it isn't configured it returns an error, which fails closed. The test suite never calls it.

## Current status (honest)

- With `NullJudge` the gate is only the fail-closed baseline (`eval/REPORT_GATE_null.md`): nothing is ever APPROVEd, harm cases the rules miss end up in REVIEW instead of being allowed, and REVIEW volume is large. That trades missed harm for human-review load; it is not a detection gain.
- **No real model judge is connected yet**, so there are no real before/after numbers. To get them, a judge must be configured and run on the 100k set and on the held-out sets, and its own error rate reported, including REVIEW volume and benign APPROVE rate.
