"""JMGL v0.4 ensemble: deterministic rules + learned classifier, fail-closed.

evaluate_action_ensemble() combines the unchanged rule engine (jmgl.engine) with
the learned category classifier (jmgl.classifier) under a documented, safety-first
merge policy calibrated on the DEV split only (eval/calibrate.py):

  1. Self-harm / crisis always wins: if the rule stage escalates, or the
     classifier's self-harm probability is high, return ESCALATE with resources.
  2. Benign look-alike rescue: if ONLY the classifier flags harm, the rule stage
     did not, a mitigation cue is present (educational / fairness / own-account /
     consent / fiction) and no covert-harm cue is present, trust ALLOW.
  3. Otherwise any harm vote wins (fail-closed): rule harm and classifier harm ->
     rule's decision (keeps JL-06 MODIFY); rule-only harm -> rule; classifier-only
     harm -> classifier's mapped decision (this catches paraphrased harm the
     regex rules miss).
  4. If both say benign -> ALLOW.

If the classifier is unavailable (missing model files or fastembed), it falls
back to the rule engine alone, so the layer never crashes (fail-closed).
"""
from __future__ import annotations
from typing import Optional

from .engine import evaluate_action, Verdict, CRISIS_RESOURCES
from . import classifier as C
from .features import signal_features, FEATURE_NAMES

ENSEMBLE_VERSION = "jmgl-0.4.1-ensemble"
SELFHARM_PROB = 0.40
# Confident-benign rescue: minimum classifier probability on a benign_* category
# required to overturn a rule-stage false positive (calibrated on the DEV split).
BENIGN_RESCUE_PROB = 0.90
_MIT = ("mit_fair", "mit_defensive", "mit_own", "mit_consent", "mit_fiction")
_HARMCUE = ("harm_covert", "harm_impersonate")
_FIDX = {n: i for i, n in enumerate(FEATURE_NAMES)}


def _is_harm(dec: str) -> bool:
    return dec in ("BLOCK", "MODIFY")


def evaluate_action_ensemble(request: str, context: Optional[dict] = None, *, with_grace: bool = True, **kw) -> Verdict:
    v = _ensemble_decision(request, context, **kw)
    if with_grace:
        try:
            from . import grace as _grace
            sc = _grace.score_components(request, context, v)
            v.grace_force = sc["grace_force"]
            v.grace = {**sc, "threshold": _grace.load_config()["threshold_pass"], "version": _grace.GRACE_VERSION}
        except Exception:
            pass
    return v


def _ensemble_decision(request: str, context: Optional[dict] = None, **kw) -> Verdict:
    rule_v = evaluate_action(request, context, **kw)
    if not C.is_available():
        return rule_v

    cl = C.classify(request, context)
    clf_dec = cl["decision"]
    feats = signal_features(request, context)
    mit = any(feats[_FIDX[m]] for m in _MIT)
    harmcue = any(feats[_FIDX[h]] for h in _HARMCUE)

    # 1) self-harm / crisis
    if rule_v.decision == "ESCALATE" or (cl["category"] == "selfharm" and cl["prob"] >= SELFHARM_PROB):
        if rule_v.decision == "ESCALATE":
            return rule_v
        return Verdict("ESCALATE", "JL-08",
                       "This sounds like you may be going through something very painful. You deserve support from a real person right now.",
                       resources=list(CRISIS_RESOURCES),
                       signals={"classifier_category": cl["category"], "classifier_prob": round(cl["prob"], 3)})

    rh, kh = _is_harm(rule_v.decision), _is_harm(clf_dec)

    # 2) benign look-alike rescue
    if kh and not rh and mit and not harmcue:
        return Verdict("ALLOW", "JL-00",
                       "No prohibited intent detected; mitigating framing (educational, fairness, own-account, consent, or fiction) outweighs a weak harm signal.",
                       signals={"classifier_category": cl["category"], "classifier_prob": round(cl["prob"], 3)})

    # 2b) confident-benign rescue (fixes rule-stage false positives). The rules
    #     flagged harm but the learned classifier is highly confident this is a
    #     benign look-alike (educational / own-account / fairness / consent /
    #     fiction), a mitigation cue is present, it is not a crisis, and NO
    #     laundering/hard-harm cue (covert, impersonation-for-credentials,
    #     phishing-authoring, elder-exploit, discriminatory proxy) is present.
    if (rh and not kh and cl["category"].startswith("benign_")
            and cl["prob"] >= BENIGN_RESCUE_PROB and mit
            and not feats[_FIDX["harm_covert"]]
            and rule_v.decision != "ESCALATE"):
        from .grace import _hard_harm_override
        if _hard_harm_override(request, context) is None:
            return Verdict("ALLOW", "JL-00",
                           "The rules flagged this, but the learned classifier is highly confident it is a "
                           "benign look-alike (%s, p=%.3f) with mitigating framing and no laundering cue." % (cl["category"], cl["prob"]),
                           signals={"classifier_category": cl["category"], "classifier_prob": round(cl["prob"], 3),
                                    "rescued_from": rule_v.decision})

    # 3) any harm vote wins (fail-closed)
    if rh and kh:
        chosen = rule_v if rule_v.decision == "MODIFY" else (rule_v if clf_dec == "MODIFY" else rule_v)
        return chosen
    if rh and not kh:
        return rule_v
    if kh and not rh:
        reason = ("The learned classifier identified this as %s, a prohibited category, even though the "
                  "keyword rules did not fire (paraphrased or indirect request)." % cl["category"])
        return Verdict(clf_dec, "JL-ML",
                       reason,
                       signals={"classifier_category": cl["category"], "classifier_prob": round(cl["prob"], 3)})

    # 4) both benign -- but never pass a clear laundering/hard-harm cue on wording
    #    alone (covert, phishing-authoring, elder-exploit, impersonation-for-creds,
    #    discriminatory proxy). Route those to a person instead of ALLOW.
    if rule_v.decision == "ALLOW":
        from .grace import _hard_harm_override
        _ovr = _hard_harm_override(request, context)
        if _ovr is not None:
            return Verdict("ESCALATE", "JL-HARMCUE",
                           "No category rule fired, but a clear harm cue is present (%s); routing to a person." % _ovr,
                           resources=None,
                           signals={"classifier_category": cl["category"], "classifier_prob": round(cl["prob"], 3)})
    return rule_v
