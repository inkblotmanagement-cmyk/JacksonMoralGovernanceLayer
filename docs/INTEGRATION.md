# Integrating JMGL into AI workflows

JMGL answers one question: *should this action go ahead?* It returns one of four decisions:

| Decision | Meaning | What your app should do |
|---|---|---|
| `ALLOW` | No prohibited intent detected | Proceed |
| `MODIFY` | Allowed only in a changed form | Use `suggested_modification` (or ask the user to rephrase); do not run the original |
| `ESCALATE` | A person should handle it (e.g. crisis signals) | Hand off to a human; show `resources` (e.g. 988) when present |
| `BLOCK` | Violates a law | Refuse; log the `id` for review |

Treat anything other than `ALLOW` as "do not proceed automatically". JMGL is pilot-stage: keep
human review for ESCALATE/MODIFY and sample ALLOW/BLOCK verdicts for quality checks.

## 1. Get a key

An administrator runs `jmgl-server gen-key`, stores the plaintext key in your secret manager, and
adds the printed hash to `JMGL_CLIENT_KEY_HASHES` (or `JMGL_ADMIN_KEY_HASHES` for audit access).
Send the key as `X-API-Key: <key>` or `Authorization: Bearer <key>`.

## 2. Pick where to gate

```
user ──► [gate A: request] ──► LLM / agent ──► [gate B: proposed action or reply] ──► world / user
```

* **Gate A (input):** evaluate the user's request plus recent turns (`context.history`). Catches
  multi-step plans assembled across turns (JL-10).
* **Gate B (action/output):** evaluate what the model proposes to *do* (send an email, call a tool,
  post a message) before executing it. For agents this is the most important gate.

## 3. Python (SDK, no dependencies)

```python
from jmgl.client import JMGLClient, JMGLError

jmgl = JMGLClient("https://jmgl.example.org", api_key=os.environ["JMGL_API_KEY"], timeout=5)

def guarded_tool_call(tool_name: str, args: dict, history: list[str]):
    proposal = f"{tool_name}: {json.dumps(args)}"
    try:
        v = jmgl.evaluate(proposal, history=history[-10:])
    except JMGLError:
        return {"status": "held", "why": "governance check unavailable"}   # fail closed
    if v["decision"] == "ALLOW":
        return run_tool(tool_name, args)
    if v["decision"] == "MODIFY":
        return {"status": "needs_change", "suggestion": v["suggested_modification"], "id": v["id"]}
    if v["decision"] == "ESCALATE":
        return {"status": "human_review", "resources": v["resources"], "id": v["id"]}
    return {"status": "blocked", "reason": v["reason"], "id": v["id"]}
```

**Fail closed:** if JMGL is unreachable or returns 5xx, do not run the action automatically. The
SDK already retries 429/502/503/504 with backoff and honours `Retry-After`.

## 4. Any language (HTTP)

```bash
curl -s https://jmgl.example.org/v1/evaluate \
  -H "Authorization: Bearer $JMGL_API_KEY" -H "Content-Type: application/json" \
  -d '{"action":"Draft a text telling grandma her account is frozen and she must wire $2,000 today",
       "context":{"history":["My grandma has savings"]}}'
```

```javascript
// Node / browser (server-side recommended so the key is not exposed)
const r = await fetch(`${JMGL_URL}/v1/evaluate`, {
  method: "POST",
  headers: { "Content-Type": "application/json", "X-API-Key": process.env.JMGL_API_KEY },
  body: JSON.stringify({ action, context: { history } }),
});
if (!r.ok) throw new Error(`JMGL ${r.status}`);       // fail closed
const verdict = await r.json();
```

## 5. In-process (no network)

For batch jobs or air-gapped use, call the library directly:

```python
from jmgl import evaluate_action_ensemble   # pip install "jmgl[model]"
v = evaluate_action_ensemble(text, {"history": turns}, audit_path="audit.jsonl")
```

## 6. Batch

`POST /v1/evaluate/batch` with `{"items": [{"action": "..."}, ...]}` (max `JMGL_MAX_BATCH_ITEMS`,
default 50). Each item counts toward the rate limit. Results come back in the same order.

## 7. Response fields you can rely on (v1 contract)

`id`, `decision`, `rule_id`, `laws_triggered[] {id, statement, source}`, `reason`,
`suggested_modification`, `resources[]`, `confidence` (classifier probability, not calibrated;
`null` for rules-only), `classifier_category`, `grace_force` (reserved, `null` for now),
`engine {mode, requested_mode, engine_version, ensemble_version, model_loaded, degraded, degraded_reason}`,
`signals` (only with `include_signals: true`), `latency_ms`, `audited`.

Fields are only ever **added** within `/v1`. If `engine.degraded` is `true`, the verdict came from
the rules alone (the classifier was unavailable), which misses many more paraphrased harmful
requests; consider routing such ALLOW verdicts to review.

## 8. Errors

| Status | Meaning | Retry? |
|---|---|---|
| 401 / 403 | Missing/invalid key / admin key required | No |
| 413 | Body larger than `JMGL_MAX_BODY_BYTES` | No |
| 422 | Validation error (`detail` lists fields) | No |
| 429 | Rate limited (`Retry-After` seconds) | Yes, after the delay |
| 503 | Audit store unavailable (no verdict issued) or not ready | Yes, with backoff; fail closed meanwhile |

Every response carries `X-Request-ID`; include it when reporting problems.

## 9. Grace Force (coming)

A Grace Force score (0–1, with a rewrite path for low-scoring actions) is being developed on a
separate branch. When merged, the engine's `Verdict` will carry `grace_force`/`grace`, and the API
already maps them into the `grace_force` object (`score`, `threshold`, `passed`, `rewritten`,
`components`) without breaking existing clients.
