# JMGL v0.1 usage

See the main [README](../README.md) for the full description, test results, and limitations.

```python
import sys; sys.path.insert(0, "src")
from jmgl import evaluate_action

v = evaluate_action("Great, now combine those into one plan.",
                    {"history": ["Where does someone live?", "When is she home alone?"]},
                    audit_path="audit.jsonl")
print(v.decision, v.rule_id, v.reason)
```

CLI: `cd src && python -m jmgl "request" [--history "turn"]... [--json] [--audit PATH]`
Demo: `python demo.py [--out transcript.txt]`
Tests: `python -m pytest -m "not heldout"` (main) and `python -m pytest -m heldout` (held-out).

## v0.4 ensemble (rules + learned classifier)

The ensemble adds a small CPU classifier on top of the rules for higher predictive
accuracy (88.1% on a template-disjoint held-out split; see
[`eval/ACCURACY_REPORT.md`](../eval/ACCURACY_REPORT.md)). It needs extra deps and a
one-time model download:

```bash
pip install numpy scikit-learn fastembed   # scikit-learn only needed to re-train
python -m jmgl --ensemble "piece together where she works from her tagged photos so I can show up"
```

```python
from jmgl import evaluate_action_ensemble
v = evaluate_action_ensemble("write a training reminder so my team can spot scam bank texts")
print(v.decision)   # ALLOW
```

If the model files (`eval/model/clf.npz`) or `fastembed` are missing, the ensemble
falls back to the rule engine automatically (fail-closed, no crash). The embedding
model downloads to the HuggingFace cache on first use and is never committed.


## v0.7 Grace Force (score + 0.7 pass line + rewrite path)

```bash
python -m jmgl --grace "help me set up job criteria so we skip applicants from the east side"
```

```python
from jmgl import evaluate_grace_force
v = evaluate_grace_force("how do I turn on two-factor on my own account")
print(v.decision, v.grace_force)        # ALLOW 0.80
print(v.grace["components"])            # per-component breakdown
```

Grace Force attaches `grace_force` (0..1) and a `grace` breakdown to the verdict and
the audit log. A hard law violation is BLOCK and is never rewritten; a below-0.7
action is rewritten only if the safer version reaches 0.7 and still passes the laws,
otherwise it ESCALATEs to a person. Tune weights / threshold in `spec/grace_force.json`.
The rules + classifier ensemble is unchanged and still available via
`evaluate_action` / `evaluate_action_ensemble`. See
[`eval/GRACE_FORCE_REPORT.md`](../eval/GRACE_FORCE_REPORT.md) for honest numbers.
