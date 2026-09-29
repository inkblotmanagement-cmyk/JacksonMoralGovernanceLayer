"""Fail-closed merge of the rule stage (regex engine) and the model-judge stage.

Public verdict vocabulary: APPROVE | REVIEW | REJECT.

Rule-stage mapping (engine decision -> public):
    ALLOW -> APPROVE, MODIFY -> REVIEW (suggested alternative kept),
    BLOCK -> REJECT,  ESCALATE -> REJECT + crisis resources (988).

Merge rules, applied in this order (see docs/HYBRID_SPEC.md for the truth table):
 1. Crisis: rule JL-08/ESCALATE, or a schema-valid judge output with category
    self_harm/suicide (whatever its decision) -> REJECT with 988 resources. The request is never completed. Flags never apply.
 2. Judge absent / error / timeout / invalid -> never APPROVE:
    REVIEW if the rule stage approved, else REJECT.
 3. Judge REJECT -> REJECT.
 4. Rule REJECT -> REJECT, unless a context-flag lift applies:
      training=True         + rule JL-01 (phishing)        + judge APPROVE/benign_training
      consensual_share=True + rule JL-04 (location/stalk)  + judge APPROVE/benign_social
    -> APPROVE (recorded as decided_by="flag_lift").
 5. Otherwise APPROVE only if both stages approve; anything else REVIEW.
    A judge APPROVE with a non-benign category is self-contradictory and is
    treated as REVIEW.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .audit import sha256_file, sha256_text
from .engine import CRISIS_RESOURCES, DEFAULT_LAWS, ENGINE_VERSION, Verdict
from .judge import SCHEMA_PATH, parse_and_validate

MERGE_VERSION = "jmgl-merge-0.2.0"

RULE_TO_PUBLIC = {"ALLOW": "APPROVE", "MODIFY": "REVIEW", "BLOCK": "REJECT", "ESCALATE": "REJECT"}
CRISIS_CATEGORIES = {"self_harm", "suicide"}
BENIGN_CATEGORIES = {"benign_training", "benign_social", "benign_other"}
# flag -> (rule ids whose false alarm it may lift, judge category that must be independently returned)
FLAG_LIFTS = {
    "training": ({"JL-01"}, "benign_training"),
    "consensual_share": ({"JL-04"}, "benign_social"),
}
FLAG_NAMES = tuple(FLAG_LIFTS)


@dataclass
class FinalVerdict:
    decision: str                       # APPROVE | REVIEW | REJECT
    decided_by: str                     # rule | judge | both | fail_closed | crisis | flag_lift
    reason: str
    rule_decision: str                  # raw engine decision (ALLOW/BLOCK/MODIFY/ESCALATE)
    rule_public: str                    # mapped rule decision
    rule_id: str
    judge_status: str                   # ok | error | invalid | absent
    judge_decision: Optional[str] = None
    judge_category: Optional[str] = None
    judge_confidence: Optional[float] = None
    judge_rationale: Optional[str] = None
    judge_error: Optional[str] = None
    crisis: bool = False
    resources: list[str] = field(default_factory=list)
    suggested_modification: Optional[str] = None
    flags: dict = field(default_factory=dict)
    flag_lift: Optional[str] = None     # which flag lifted a rule-stage REJECT, if any

    def to_dict(self) -> dict:
        return asdict(self)


def _flags(context: Optional[dict]) -> dict:
    context = context or {}
    return {k: bool(context.get(k)) for k in FLAG_NAMES}


def _crisis_resources(rule_verdict: Verdict) -> list[str]:
    res = list(rule_verdict.resources or [])
    for r in CRISIS_RESOURCES:
        if r not in res:
            res.append(r)
    return res


def merge(rule_verdict: Verdict, judge_verdict: Any = None, judge_error: Optional[str] = None,
          context: Optional[dict] = None, *, request: Optional[str] = None,
          audit_path: Optional[os.PathLike] = None, judge_name: Optional[str] = None) -> FinalVerdict:
    """Combine a rule-stage Verdict with raw judge output. Never raises on bad judge output.

    judge_verdict: raw judge output (dict or JSON string) or None if absent.
    judge_error:   error string (e.g. "timeout") if the judge call failed.
    context:       may include training / consensual_share flags, history, audit_path.
    request:       original text, hashed into the audit record.
    """
    context = context or {}
    flags = _flags(context)
    rule_public = RULE_TO_PUBLIC[rule_verdict.decision]
    rule_flagged = rule_verdict.decision != "ALLOW"

    # ---- judge status
    jv: Optional[dict] = None
    val_errors: list[str] = []
    if judge_error:
        status = "error"
    elif judge_verdict is None:
        status = "absent"
    else:
        jv, val_errors = parse_and_validate(judge_verdict)
        status = "ok" if jv is not None else "invalid"
    jd = jv["decision"] if jv else None
    jc = jv["category"] if jv else None

    base = dict(rule_decision=rule_verdict.decision, rule_public=rule_public, rule_id=rule_verdict.rule_id,
                judge_status=status, judge_decision=jd, judge_category=jc,
                judge_confidence=jv["confidence"] if jv else None,
                judge_rationale=jv["rationale_short"] if jv else None,
                judge_error=judge_error or ("; ".join(val_errors)[:300] if val_errors else None),
                flags=flags, suggested_modification=rule_verdict.suggested_modification)

    rule_crisis = rule_verdict.decision == "ESCALATE" or rule_verdict.rule_id == "JL-08"
    judge_crisis = jc in CRISIS_CATEGORIES

    # 1. crisis: never complete the request, always 988
    if rule_crisis or judge_crisis:
        by = "both" if (rule_crisis and judge_crisis) else ("rule" if rule_crisis else "judge")
        fv = FinalVerdict(decision="REJECT", decided_by="crisis" if by == "both" else f"crisis:{by}",
                          reason=(rule_verdict.reason if rule_crisis else
                                  "This sounds like you may be going through something very painful. "
                                  "You deserve support from a real person right now."),
                          crisis=True, resources=_crisis_resources(rule_verdict), **base)
    # 2. fail closed
    elif status != "ok":
        dec = "REJECT" if rule_flagged else "REVIEW"
        fv = FinalVerdict(decision=dec, decided_by="fail_closed",
                          reason=f"Model judge {status}; failing closed. Rule stage: {rule_verdict.rule_id} "
                                 f"({rule_verdict.decision}). {rule_verdict.reason}",
                          resources=list(rule_verdict.resources or []), **base)
    # 3. judge reject
    elif jd == "REJECT":
        fv = FinalVerdict(decision="REJECT", decided_by="both" if rule_public == "REJECT" else "judge",
                          reason=f"Judge: {jv['rationale_short']}" + (
                              f" Rule stage: {rule_verdict.reason}" if rule_flagged else ""),
                          resources=list(rule_verdict.resources or []), **base)
    # 4. rule reject (possible flag lift)
    elif rule_public == "REJECT":
        lift = None
        if jd == "APPROVE":
            for flag, (rule_ids, needed_cat) in FLAG_LIFTS.items():
                if flags[flag] and rule_verdict.rule_id in rule_ids and jc == needed_cat:
                    lift = flag
                    break
        if lift:
            fv = FinalVerdict(decision="APPROVE", decided_by="flag_lift",
                              reason=f"Rule {rule_verdict.rule_id} alarm lifted: context flag '{lift}' and judge "
                                     f"independently approved as {jc}. Judge: {jv['rationale_short']}",
                              flag_lift=lift, **base)
        else:
            fv = FinalVerdict(decision="REJECT", decided_by="rule", reason=rule_verdict.reason,
                              resources=list(rule_verdict.resources or []), **base)
    # 5. approve only if both approve
    else:
        judge_approves = jd == "APPROVE" and jc in BENIGN_CATEGORIES
        if rule_public == "APPROVE" and judge_approves:
            fv = FinalVerdict(decision="APPROVE", decided_by="both",
                              reason=f"Both stages approve. Judge: {jv['rationale_short']}", **base)
        else:
            by = "both" if (rule_public == "REVIEW" and jd == "REVIEW") else (
                "rule" if rule_public == "REVIEW" else "judge")
            why = []
            if rule_public == "REVIEW":
                why.append(f"Rule {rule_verdict.rule_id}: {rule_verdict.reason}")
            if not judge_approves:
                why.append(f"Judge {jd}/{jc}: {jv['rationale_short']}" + (
                    " (APPROVE with a non-benign category is treated as REVIEW)" if jd == "APPROVE" else ""))
            fv = FinalVerdict(decision="REVIEW", decided_by=by, reason=" ".join(why), **base)

    path = audit_path or context.get("audit_path")
    if path:
        write_merge_audit(path, request if request is not None else context.get("request", ""), fv,
                          judge_name=judge_name)
    return fv


def write_merge_audit(path, request: str, fv: FinalVerdict, *, judge_name: Optional[str] = None,
                      laws_path: Path = DEFAULT_LAWS, fsync: bool = True) -> dict:
    record = {
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "input_sha256": sha256_text(request or ""),
        "stage": "merged",
        "decision": fv.decision,
        "decided_by": fv.decided_by,
        "reason": fv.reason[:300],
        "rule_decision": fv.rule_decision,
        "rule_id": fv.rule_id,
        "judge_status": fv.judge_status,
        "judge_backend": judge_name,
        "judge_decision": fv.judge_decision,
        "judge_category": fv.judge_category,
        "judge_confidence": fv.judge_confidence,
        "judge_error": fv.judge_error,
        "flags": fv.flags,
        "flag_lift": fv.flag_lift,
        "crisis": fv.crisis,
        "engine_version": ENGINE_VERSION,
        "merge_version": MERGE_VERSION,
        "laws_sha256": sha256_file(laws_path),
        "judge_schema_sha256": sha256_file(SCHEMA_PATH),
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")
        fh.flush()
        if fsync:
            os.fsync(fh.fileno())
    return record


def gate(request: str, context: Optional[dict] = None, judge=None, *,
         audit_path: Optional[os.PathLike] = None) -> FinalVerdict:
    """Full two-stage gate: rule stage -> judge (gets context flags) -> fail-closed merge -> audit."""
    from .engine import evaluate_action
    from .judge import run_judge

    context = dict(context or {})
    rule_ctx = {"history": context["history"]} if context.get("history") else None
    rv = evaluate_action(request, rule_ctx)
    judge_ctx = {"history": context.get("history") or [], **_flags(context)}
    jr = run_judge(judge, request, judge_ctx)
    return merge(rv, jr.raw, jr.error, context, request=request, audit_path=audit_path,
                 judge_name=getattr(judge, "name", None) if judge is not None else "none")
