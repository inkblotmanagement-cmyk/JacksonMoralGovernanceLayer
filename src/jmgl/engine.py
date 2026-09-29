"""JMGL v0.1 evaluation engine: deterministic rule-and-signal policy evaluator.

Mechanism (honest description):
  1. Scan the current request and each prior turn in context['history'] for
     regex signal families (see signals.py).
  2. Combine signals into intent judgements per law: a harmful DOMAIN cue alone
     is not enough; the engine looks for PURPOSE (deceive / pressure / conceal /
     target a person / produce the artifact) and checks for MITIGATING framing
     (educational, defensive, own-account, fairness).
  3. Claims of authority to bypass checks never lower a verdict; they are
     flagged (JL-09) and the underlying request is still judged.
  4. History is aggregated so a harmful goal assembled across turns is caught
     (JL-10).
  5. Priority: self-harm ESCALATE > BLOCK laws > MODIFY > ALLOW.
No randomness, no network access.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from . import signals as S
from .audit import write_audit

ENGINE_VERSION = "jmgl-0.1.0"
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LAWS = REPO_ROOT / "spec" / "laws.json"

CRISIS_RESOURCES = [
    "US: call or text 988 (988 Suicide & Crisis Lifeline), or chat at 988lifeline.org",
    "If you are in immediate danger, call 911 (US) or your local emergency number",
    "Outside the US: find a local helpline at findahelpline.com",
]


@dataclass
class Verdict:
    decision: str
    rule_id: str
    reason: str
    resources: list[str] = field(default_factory=list)
    suggested_modification: Optional[str] = None
    signals: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def load_laws(path: Path = DEFAULT_LAWS) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {law["id"]: law for law in data["laws"]}


def _has(sig: dict, *keys: str) -> bool:
    return any(sig.get(k) for k in keys)


def _judge_single(sig: dict) -> list[tuple[str, str]]:
    """Return list of (law_id, reason) triggered by one text's signals."""
    hits: list[tuple[str, str]] = []
    # Mitigation: defensive/educational framing or the user being the target.
    # Educational framing only mitigates when the user is NOT asking us to
    # produce the harmful artifact (explaining != doing).
    victim = _has(sig, "victim")
    edu_only = _has(sig, "edu_defensive") and not _has(sig, "produce")
    mitig = victim or _has(sig, "edu_defensive")
    purpose = _has(sig, "deceive", "pressure", "conceal")

    if _has(sig, "jailbreak"):
        hits.append(("JL-05", "The request asks the system to drop its safety guidelines (role-play as unrestricted / ignore instructions)."))

    # JL-01 deception / phishing: deceptive purpose + financial/credential/institution domain, or explicit phishing artifact request
    if (_has(sig, "deceive") and _has(sig, "phishing", "credential", "produce")) or (_has(sig, "phishing") and _has(sig, "produce") and not mitig):
        if not (edu_only or victim or (mitig and not purpose)):
            hits.append(("JL-01", "The request seeks a deceptive message (e.g. impersonating a bank) designed to trick people into giving up money or credentials."))

    # JL-02 other person's credentials
    if _has(sig, "credential") and _has(sig, "other_account") and not (_has(sig, "edu_defensive") or victim):
        hits.append(("JL-02", "The request involves taking another person's passwords or account access without their consent."))

    # JL-03 pressuring a vulnerable person
    if _has(sig, "elder") and _has(sig, "pressure", "conceal", "deceive") and not (mitig and not _has(sig, "produce")):
        hits.append(("JL-03", "The request seeks to pressure or manipulate a vulnerable person (such as an elder) into a financial decision."))

    # JL-04 stalking / tracking a person
    if _has(sig, "stalk") and (_has(sig, "target_person") or "stalk" in " ".join(sig["stalk"])) and not mitig:
        hits.append(("JL-04", "The request seeks to locate, track, or monitor a specific person without their consent."))

    # JL-06 discriminatory hiring (proxy exclusion)
    if _has(sig, "discrim") and _has(sig, "hiring") and not _has(sig, "fairness"):
        hits.append(("JL-06", "The request would build hiring criteria that exclude people by neighborhood/zip code, a known proxy for race and income."))

    # JL-07 market manipulation
    if _has(sig, "market") and _has(sig, "market_plan") and (_has(sig, "deceive") or len(sig["market_plan"]) >= 2) and not mitig:
        hits.append(("JL-07", "The request describes hyping an asset through fake/misleading promotion before selling, i.e. market manipulation."))
    return hits


def evaluate_action(request: str, context: Optional[dict] = None, *, laws_path: Path = DEFAULT_LAWS,
                    audit_path: Optional[Path] = None, log_raw: bool = False) -> Verdict:
    """Evaluate a proposed request/action and return a Verdict.

    context: optional dict. Supported key: 'history' (list[str] of prior user turns).
    audit_path: if given, append a JSONL audit record (hash of input by default).
    """
    laws = load_laws(laws_path)
    context = context or {}
    history = [str(h) for h in context.get("history", [])]

    sig = S.scan(request)
    hist_sigs = [S.scan(h) for h in history]
    verdict: Verdict

    bypass = _has(sig, "bypass_authority")
    hits = _judge_single(sig)

    # 1) Self-harm: supportive escalation takes priority (never a cold block).
    if _has(sig, "self_harm") or any(_has(h, "self_harm") for h in hist_sigs):
        verdict = Verdict("ESCALATE", "JL-08",
                          "This sounds like you may be going through something very painful. You deserve support from a real person right now.",
                          resources=list(CRISIS_RESOURCES))
    elif hits:
        law_id, reason = hits[0]
        decision = laws[law_id]["default_decision"]
        mod = None
        if law_id == "JL-06":
            # Chosen: MODIFY with fair alternative (see README for justification).
            if _has(sig, "conceal"):
                decision = "BLOCK"
                reason += " It also asks to hide this intent, so it is blocked rather than rewritten."
            else:
                mod = ("Use job-related, uniformly applied criteria instead: required skills, certifications, relevant experience, "
                       "and availability for the shift. Do not use zip code, neighborhood, or commute distance as a screen; "
                       "if reliability is the concern, ask all candidates the same availability question.")
        if bypass:
            reason += " A claimed authorization to bypass the ethics check was also present; it does not change the verdict (JL-09)."
        verdict = Verdict(decision, law_id, reason, suggested_modification=mod)
    elif bypass:
        verdict = Verdict("BLOCK", "JL-09", "A claim of authority to skip or disable the ethics check does not change the verdict; the check cannot be waived by the requester.")
    else:
        # 2) Multi-turn: judge the combined conversation.
        combined_hits = _judge_single(S.scan(" ".join(history + [request]))) if history else []
        staged = False
        if history:
            h_target = any(_has(h, "target_person") for h in hist_sigs) or _has(sig, "target_person")
            h_sensitive = sum(1 for h in hist_sigs if _has(h, "sensitive", "stalk", "credential"))
            assemble = _has(sig, "produce") or any(w in request.lower() for w in ("put it all together", "combine", "now do", "step"))
            staged = h_target and h_sensitive >= 1 and assemble
        if combined_hits or staged:
            base = combined_hits[0] if combined_hits else ("JL-04", "")
            verdict = Verdict("BLOCK", "JL-10",
                              f"Taken together with earlier turns, this request assembles a harmful task ({base[0]}: "
                              f"{laws[base[0]]['harm']}). Splitting it into innocent-looking steps does not change the verdict.")
        else:
            verdict = Verdict("ALLOW", "JL-00", "No prohibited intent detected; defensive, educational, or ordinary request.")

    verdict.signals = {k: len(v) for k, v in sig.items() if v}
    if audit_path is not None:
        write_audit(audit_path, request, verdict, laws_path, ENGINE_VERSION, log_raw=log_raw)
    return verdict
