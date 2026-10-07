"""Grace Force: a measurable 0..1 score toward aligning an action with human
flourishing, with a configurable 0.7 pass line and a deterministic rewrite path.

Grace Force combines four components (weights in spec/grace_force.json):
  * human_benefit         - how much the action helps the people it touches
  * harm_avoided          - no JMGL law (JL-00..JL-10) violated; strong penalty
                            for irreversible-harm categories
  * long_term_flourishing - durable good: skills, income, well-being over time
  * confidence            - how sure the layer is; low confidence lowers the
                            score AND routes to a person

Decision (evaluate_grace_force):
  1. Self-harm / crisis            -> ESCALATE with resources (never scored away).
  2. Hard law BLOCK                -> BLOCK regardless of score; NEVER rewritten.
  3. confidence < route threshold  -> ESCALATE (route to a person).
  4. grace_force >= threshold      -> ALLOW (pass).
  5. grace_force <  threshold      -> rewrite path; return the rewrite only if it
     reaches the threshold AND still passes the laws AND stays below the harm cap;
     otherwise ESCALATE.

HONESTY: harm_avoided and confidence are grounded in the rules + learned
classifier; human_benefit and long_term_flourishing are lexical/categorical
PROXIES, the weakest parts of the score. This is a transparent heuristic, not an
independent measurement of real benefit. See eval/GRACE_FORCE_REPORT.md.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from .engine import evaluate_action, Verdict, CRISIS_RESOURCES
from . import classifier as C


def _base_verdict(request, context):
    """Base decision for Grace: the rules+classifier ensemble (falls back to rules
    alone if the classifier is unavailable)."""
    from .ensemble import _ensemble_decision
    return _ensemble_decision(request, context)

GRACE_VERSION = "grace-force-0.7.1"
_CONFIG_PATH = Path(__file__).resolve().parents[2] / "spec" / "grace_force.json"
_CONFIG: Optional[dict] = None

HARM_CATEGORIES = {"authclaim", "creds", "elderfin", "hiring", "jailbreak",
                   "multiturn", "phishing", "pumpdump", "stalking", "selfharm"}

_BENEFIT_WORDS = re.compile(
    r"\b(help|helps?|support|protect|secure|safe(?:ly|guard)?|recover|learn|teach|train(?:ing)?|"
    r"report|budget|welcome|improve|assist|advice|avoid|prevent|explain|understand|verify|guide)\b", re.I)
_FLOURISH_WORDS = re.compile(
    r"\b(skill|skills|educat|literacy|career|financ|save|saving|savings|retire|retirement|"
    r"well-?being|health|grow|growth|future|long-?term|invest(?:ing)?|income|opportunit|independ|stability)\b", re.I)
_CONSENT_WORDS = re.compile(r"\b(consent|with (?:their|everyone'?s?) (?:ok|permission)|agreed|opt[- ]?in|my own)\b", re.I)
_COVERT = re.compile(r"\b(secretly|quietly|without (?:them|her|his|their|him|anyone) (?:knowing|agreeing|noticing|finding out|realizing)|without telling|sneak|behind (?:his|her|their) back|burner|sockpuppet|throwaway|while (?:she|he|they)(?:\s+\w+){0,2}\s+(?:asleep|sleep|sleeps|sleeping|shower|showers|showering|out|away)|without (?:her|his|their|anyone(?:\'?s)?) (?:knowledge|consent|agreement)|(?:does|do|would|will|did)(?:\s*n'?t| not) (?:mention|tell|inform|notify|let (?:him|her|them|anyone))|(?:don'?t|do not|never|not) (?:tell|mention|inform|notify) (?:his|her|their|the|my|other|anyone|them|him|her)|keep (?:it|this|that) (?:from|secret from|hidden from)|without (?:the )?(?:other )?(?:relatives|family|siblings|kids) (?:knowing|finding out))\b", re.I)
_IMPERSONATE = re.compile(r"\b(looks? like it'?s? from|styled? like|pose as|posing as|pretend(?:ing)? to be|in the voice of)\b", re.I)
# Laundering cues the composite score can miss when benign wording ("fair",
# "for safety", "with consent") suppresses the rules/classifier. These force a
# route-to-human (ESCALATE) even if the score would otherwise pass.
_DISCRIM_PROXY = re.compile(
    r"\b(certain (?:zip ?codes?|parts? of town|neighbou?rhoods?|areas)|zip ?codes?|the projects|section 8|"
    r"(?:east|west|south|north) side|past the highway|rough (?:parts|areas|neighbou?rhoods?|sounding)|"
    r"'?rough'? ?(?:sounding )?address)\b", re.I)
_EXCLUDE_VERB = re.compile(r"\b(?:screen(?:s|ed|ing)? out|filter(?:s|ed|ing)? out|exclud\w*|skips?|skipped|skipping|rejects?|rejected|rejecting|auto-?rejects?|auto-?rejected|weed(?:s|ed|ing)? out|keeps? [^.?!]*out|only want[^.?!]* who ?are?n'?t|aren'?t from|cut[^.?!]* from|bump[^.?!]* down)", re.I)
_PHISH_AUTHOR = re.compile(
    r"(?:\b(?:trick|fool|get|gets|make|makes|convince|convinces|lure|lures|prompt|prompts|dupe|dupes|deceive|deceives)\b[^.?!]{0,50}\b(?:into|to)\b[^.?!]{0,60}(?:enter|re-?enter|confirm|re-?confirm|provide|input|update|verify|submit|hand over|type|give (?:us|me)))"
    r"|(?:\b(?:email|message|page|form|text|sms|letter|site|portal|login screen)\b[^.?!]{0,70}(?:enter|re-?enter|confirm|re-?confirm|provide|input|update|verify|submit)[^.?!]{0,35}\b(?:password|passwords|login|logins|card number|card details|credential|credentials|bank|direct deposit|deposit details|account details|ssn|social security|pin|one-?time code|the code|payment (?:details|info)))",
    re.I)
# impersonation/disguise paired with a credential or login "verify" lure.
_PHISH_LURE = re.compile(
    r"\b(?:disguis\w+|impersonat\w+|masquerad\w+|spoof\w*|pose as|posing as|pretend\w*(?: to be)?|looks? like it'?s from|claiming to be|made to look like)\b"
    r"[^.?!]{0,90}\b(?:verify|confirm|re-?confirm|log ?in|sign ?in|click|enter|re-?enter|update|reset|provide|submit)\b",
    re.I)
# elder financial exploitation: get an elder to hand over control / add me to
# accounts / sign things over -- especially while concealing it from others.
_ELDER = re.compile(r"\b(elderly|senior|grandmother|grandma|grandpa|grandfather|my (?:aunt|uncle|mother|father|mom|dad|gran|nan)|aging (?:parent|mother|father)|her other relatives|his other relatives)\b", re.I)
_ELDER_GRAB = re.compile(r"\b(hand (?:me|over)|sign(?:ing)? (?:everything|the house|it all|over)|control of (?:all )?(?:her|his|their) (?:accounts|assets|money|finances|savings)|add(?:s|ed)? me to (?:his|her|their) (?:bank )?account|transfer (?:her|his|their) (?:accounts|assets|savings|money)|power of attorney|move (?:her|his|their) (?:pension|savings|money|accounts))\b", re.I)
_CRED_TARGET = re.compile(r"\b(password|passwords|login|logins|card number|ssn|social security|2fa|one-?time code|the code|pin|credential)\b", re.I)
_DEFENSIVE = re.compile(r"\b(report|recogni[sz]e|spot|detect|avoid|protect|aware|training to (?:spot|avoid)|how to tell|identify a scam)\b", re.I)


def _hard_harm_override(request: str, context: Optional[dict]) -> Optional[str]:
    """Return a reason string if the text shows a clear laundering/harm pattern that
    must not pass on score alone; else None. Defensive framing (report/recognize a
    scam) is exempted so awareness requests are not caught."""
    text = " ".join([str(h) for h in (context or {}).get("history", [])] + [request])
    if _COVERT.search(text):
        return "covert intent (e.g. secretly / quietly / without their knowledge)"
    if _DISCRIM_PROXY.search(text) and _EXCLUDE_VERB.search(text):
        return "discriminatory proxy exclusion (screening people out by area/zip)"
    if _IMPERSONATE.search(text) and _CRED_TARGET.search(text) and not _DEFENSIVE.search(text):
        return "impersonation aimed at harvesting credentials"
    if _PHISH_AUTHOR.search(text):
        return "authoring a deceptive message/page that captures passwords, card or payment details"
    if _PHISH_LURE.search(text) and not _DEFENSIVE.search(text):
        return "impersonation paired with a login/verify lure (phishing)"
    if _ELDER.search(text) and _ELDER_GRAB.search(text):
        return "pressuring an elder to hand over money/accounts or control of their finances"
    return None


def load_config(path: Optional[Path] = None) -> dict:
    global _CONFIG
    if path is not None:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    if _CONFIG is None:
        _CONFIG = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    return _CONFIG


# --------------------------------------------------------------------------- scoring
def _clf_signals(request: str, context: Optional[dict], rule_v: Verdict) -> dict:
    """Return p_harm (0..1) and confidence (0..1) and predicted category.

    Uses the learned classifier when available; otherwise derives conservative
    proxies from the deterministic rule verdict (fail-closed)."""
    if C.is_available():
        try:
            cl = C.classify(request, context)
            probs = cl.get("probs") or {}
            p_harm = sum(v for k, v in probs.items() if k in HARM_CATEGORIES)
            if not probs:  # stubbed/empty -> fall back to the predicted decision
                p_harm = 0.85 if cl["decision"] in ("BLOCK", "MODIFY") else 0.15
            return {"p_harm": min(1.0, p_harm), "confidence": float(cl.get("prob", 0.6)),
                    "category": cl.get("category", "?"), "source": "classifier"}
        except Exception:
            pass
    # rule-only fallback
    if rule_v.decision in ("BLOCK",):
        return {"p_harm": 0.9, "confidence": 0.8, "category": "rule", "source": "rule"}
    if rule_v.decision in ("MODIFY", "ESCALATE"):
        return {"p_harm": 0.6, "confidence": 0.7, "category": "rule", "source": "rule"}
    return {"p_harm": 0.15, "confidence": 0.55, "category": "rule", "source": "rule"}


def score_components(request: str, context: Optional[dict], rule_v: Verdict,
                     cfg: Optional[dict] = None) -> dict:
    cfg = cfg or load_config()
    context = context or {}
    text = " ".join([str(h) for h in (context.get("history") or [])] + [request])
    cs = _clf_signals(request, context, rule_v)
    p_harm, confidence, cat = cs["p_harm"], cs["confidence"], cs["category"]

    hard_block = rule_v.decision == "BLOCK"
    is_harm_pred = (cat in HARM_CATEGORIES) or rule_v.decision in ("BLOCK", "MODIFY")

    # harm_avoided: primarily grounded in the law verdict (no JL-00..JL-10 violation),
    # with the classifier's harm probability as a secondary caution.
    if hard_block:
        harm_avoided = 0.0
    elif rule_v.decision == "ESCALATE":
        harm_avoided = 0.0
    elif rule_v.decision == "MODIFY":
        harm_avoided = 0.45 * (1.0 - 0.5 * p_harm)   # fixable violation present
    else:  # ALLOW: no law fired; classifier caution still lowers it a little
        harm_avoided = 1.0 - 0.2 * p_harm
    if cat in set(cfg["irreversible_categories"]) and rule_v.decision != "ALLOW":
        harm_avoided = harm_avoided ** 2             # stronger penalty for irreversible harm
    harm_avoided = max(0.0, min(1.0, harm_avoided))

    # human_benefit (proxy)
    base_b = 0.1 if is_harm_pred else 0.65
    bonus_b = 0.08 * len(set(m.group(0).lower() for m in _BENEFIT_WORDS.finditer(text)))
    human_benefit = max(0.0, min(1.0, base_b + min(0.25, bonus_b) * (0.2 if is_harm_pred else 1.0)))

    # long_term_flourishing (proxy)
    base_f = 0.1 if is_harm_pred else 0.45
    bonus_f = 0.12 * len(set(m.group(0).lower() for m in _FLOURISH_WORDS.finditer(text)))
    long_term = max(0.0, min(1.0, base_f + min(0.35, bonus_f) * (0.2 if is_harm_pred else 1.0)))

    w = cfg["weights"]
    gf = (w["human_benefit"] * human_benefit + w["harm_avoided"] * harm_avoided +
          w["long_term_flourishing"] * long_term + w["confidence"] * confidence)
    gf = max(0.0, min(1.0, gf))
    return {
        "grace_force": round(gf, 4),
        "components": {"human_benefit": round(human_benefit, 4), "harm_avoided": round(harm_avoided, 4),
                       "long_term_flourishing": round(long_term, 4), "confidence": round(confidence, 4)},
        "p_harm": round(p_harm, 4), "category": cat, "score_source": cs["source"],
        "hard_block": hard_block,
    }


# --------------------------------------------------------------------------- rewrite path
_MITIGATIONS = [
    ("consent", " — only proceed with the explicit, informed consent of everyone involved"),
    ("disclosure", " — and clearly and truthfully disclose who is really sending this and why"),
    ("human_review", " — route this to a human reviewer for sign-off before anything is sent or acted on"),
    ("scope_down", " — limited strictly to my own accounts/data and to lawful, transparent purposes"),
]


_FAIR_HIRING_REWRITE = (
    "Evaluate every applicant on the same job-related factors: the skills, "
    "certifications and experience the role needs, plus availability for the shift. "
    "Ask all candidates identical questions and apply identical scoring, and base no "
    "decision on where someone lives or on any protected characteristic.")


def _candidate_texts(request: str, base_v: Verdict, p_harm: float, context: Optional[dict], cfg: dict):
    """Build rewrite candidates.

    * TRANSFORMATIVE rewrites (for a MODIFY verdict such as discriminatory hiring)
      legitimately REMOVE the harmful criterion, so they are always attempted; the
      per-candidate re-check still guards them.
    * ADDITIVE safeguards (consent / disclosure / review / scope-down) do NOT remove
      a harmful core, so they are only attempted when the base verdict is ALLOW, the
      classifier harm probability is below the cap, and the original carries no
      covert/impersonation cue. This is the anti-laundering guard: a harmful goal
      cannot be reworded into a pass."""
    cands = []
    if base_v.decision == "MODIFY":
        cands.append(("fair_criteria", _FAIR_HIRING_REWRITE))
    combined = " ".join([str(h) for h in (context or {}).get("history", [])] + [request])
    additive_ok = (base_v.decision == "ALLOW"
                   and p_harm < cfg["rewrite"]["p_harm_eligibility_cap"]
                   and not _COVERT.search(combined) and not _IMPERSONATE.search(combined))
    if additive_ok:
        acc = request
        for name, suffix in _MITIGATIONS:
            acc = acc + suffix
            cands.append((name, acc))
    return cands


def _passes(text: str, context: Optional[dict], cfg: dict):
    rv = _base_verdict(text, context)
    sc = score_components(text, context, rv, cfg)
    ok = (rv.decision != "BLOCK" and rv.decision != "ESCALATE"
          and sc["grace_force"] >= cfg["threshold_pass"]
          and sc["p_harm"] < cfg["rewrite"]["p_harm_eligibility_cap"]
          and not _COVERT.search(text) and not _IMPERSONATE.search(text))
    return ok, rv, sc





# --------------------------------------------------------------------------- entrypoint
def evaluate_grace_force(request: str, context: Optional[dict] = None, *,
                         cfg: Optional[dict] = None, audit_path: Optional[str] = None,
                         log_raw: bool = False) -> Verdict:
    cfg = cfg or load_config()
    rule_v = _base_verdict(request, context)
    sc = score_components(request, context, rule_v, cfg)
    gf = sc["grace_force"]
    grace_meta = {**sc, "threshold": cfg["threshold_pass"], "version": GRACE_VERSION,
                  "original_grace_force": sc["grace_force"],
                  "rewritten": False, "rewrite_iterations": 0, "rewrite_name": None}

    def finalize(v: Verdict) -> Verdict:
        v.grace_force = grace_meta["grace_force"]
        v.grace = grace_meta
        if audit_path is not None:
            from .audit import write_audit
            from .engine import DEFAULT_LAWS, ENGINE_VERSION
            write_audit(audit_path, request, v, DEFAULT_LAWS, ENGINE_VERSION, log_raw=log_raw)
        return v

    # 1) crisis / self-harm
    if rule_v.decision == "ESCALATE":
        return finalize(Verdict("ESCALATE", rule_v.rule_id, rule_v.reason,
                                resources=list(rule_v.resources or CRISIS_RESOURCES)))
    # 2) hard law BLOCK -> never rewritten
    if sc["hard_block"]:
        return finalize(Verdict("BLOCK", rule_v.rule_id,
                                rule_v.reason + f" (Grace Force {gf:.2f}; a hard law violation is never rewritten.)"))
    # 3) low confidence -> route to a person
    if sc["components"]["confidence"] < cfg["confidence_route_threshold"]:
        return finalize(Verdict("ESCALATE", "GF-CONF",
                                f"Grace Force {gf:.2f}; confidence {sc['components']['confidence']:.2f} is below the routing line, so this goes to a person."))
    # 3b) laundering / hard-harm override: never pass or rewrite these on score alone
    _ovr = _hard_harm_override(request, context)
    if _ovr is not None:
        return finalize(Verdict("ESCALATE", "GF-HARMCUE",
                                f"Grace Force {gf:.2f}; a clear harm cue is present ({_ovr}), so this is routed to a person rather than passed or reworded."))

    # 4) pass
    if gf >= cfg["threshold_pass"]:
        return finalize(Verdict("ALLOW", "GF-PASS",
                                f"Grace Force {gf:.2f} is at or above the {cfg['threshold_pass']} pass line."))
    # 5) rewrite path (hard BLOCK already handled above and is never rewritten)
    candidates = _candidate_texts(request, rule_v, sc["p_harm"], context, cfg)
    for i, (name, cand) in enumerate(candidates[: cfg["rewrite"]["max_iters"]], start=1):
        ok, rv2, sc2 = _passes(cand, context, cfg)
        if ok:
            grace_meta.update(grace_force=sc2["grace_force"], components=sc2["components"],
                              p_harm=sc2["p_harm"], rewritten=True, rewrite_iterations=i, rewrite_name=name)
            return finalize(Verdict("MODIFY", "GF-REWRITE",
                                    f"Original Grace Force {gf:.2f} was below the line; a safer rewrite scores {sc2['grace_force']:.2f} and passes the laws.",
                                    suggested_modification=cand))
    # 6) no safe rewrite -> escalate
    return finalize(Verdict("ESCALATE", "GF-ESCALATE",
                            f"Grace Force {gf:.2f} is below the {cfg['threshold_pass']} line and no safe rewrite reached it; sending to a person."))
