"""Deterministic non-embedding features for the JMGL classifier.

These are the engine's own regex signal families (jmgl.signals) plus the locate
and crisis detectors, expressed as a fixed-length binary/scaled vector. They give
the learned classifier access to the same purpose/mitigation cues the rules use
(educational framing, fairness, own-account, victim perspective, crisis level),
which is what separates benign look-alikes (scam-awareness, fair hiring, securing
your own account) from the real harm categories.

Computed from text only, with no network and no embedding, so they are available
identically at training and inference time. FEATURE_NAMES documents the order.
"""
from __future__ import annotations
from typing import Optional
import numpy as np

import re
from . import signals as S
from . import crisis as CR
from . import locate as LOC

# Richer mitigation / intent cues than the engine's own regexes (used only as
# classifier FEATURES, so the engine's rule behavior and its tests are unchanged).
_EXTRA_PATTERNS = {
    "mit_fair": r"\b(fair(ly|ness)?|equitab|equity|inclusiv|diverse|diversit|widen|broaden|unbiased|bias[- ]free|non-?discriminat|equal opportunit|same (?:question|criteria|factors)|skills?[- ]based|job-?related)\b",
    "mit_defensive": r"\b(recogni[sz]e|spot|detect|identify|avoid|protect|defend|prevent|report|awareness|educat|train(?:ing)?|warn|safe(?:ly|guard)?|verify|how (?:do|to).*(?:scam|trick|fraud|fool)|steer clear)\b",
    "mit_own": r"\b(my own|my (?:account|email|icloud|password|phone|laptop|wi-?fi|router|budget)|our (?:newsletter|team|staff|company)|myself)\b",
    "mit_consent": r"\b(opt[- ]?in|agreed?|consent|with (?:everyone'?s? )?(?:ok|permission)|each other|my family|share my)\b",
    "mit_fiction": r"\b(novel|short story|story|fiction|character|book|screenplay|villain|monologue|scene|plot|writing a)\b",
    "harm_covert": r"\b(without (?:them|her|his|their|him) (?:knowing|agreeing|noticing)|secretly|sneak|quietly|no questions|behind (?:his|her|their) back|while (?:she|he|they|it)'?s? (?:asleep|out|unlocked|away)|before (?:he|she|they) (?:gets?|comes?) back|throwaway|burner|sockpuppet|astroturf|no one(?:'s| is)? (?:looking|around))\b",
    "harm_impersonate": r"\b(looks? like it'?s? from|styled? like|in the voice of|pretend(?:ing)? to be|posing as|seems? to come from|appears? to come from|read back the code|reconnection charge|gift card)\b",
}
_EXTRA_RE = {k: re.compile(v, re.I) for k, v in _EXTRA_PATTERNS.items()}

SIGNAL_FAMILIES = [
    "produce", "deceive", "pressure", "conceal", "target_person", "bypass_authority",
    "jailbreak", "edu_defensive", "victim", "fairness", "phishing", "credential",
    "other_account", "elder", "stalk", "discrim", "hiring", "market", "market_plan",
    "self_harm", "sensitive",
]
# extra engineered flags
EXTRA = ["locate_hit", "crisis_self", "crisis_third", "has_history", "n_signals_scaled"] + list(_EXTRA_PATTERNS)
FEATURE_NAMES = SIGNAL_FAMILIES + EXTRA
N_FEATURES = len(FEATURE_NAMES)


def signal_features(request: str, context: Optional[dict] = None) -> np.ndarray:
    context = context or {}
    history = [str(h) for h in (context.get("history") or [])]
    combined = " ".join(history + [request]) if history else request
    sig = S.scan(combined)
    vec = [1.0 if sig.get(f) else 0.0 for f in SIGNAL_FAMILIES]
    level = CR.assess(combined)["level"]
    vec.append(1.0 if LOC.assess(combined)["hit"] else 0.0)
    vec.append(1.0 if level == "self" else 0.0)
    vec.append(1.0 if level == "third_party" else 0.0)
    vec.append(1.0 if history else 0.0)
    n_on = sum(1 for f in SIGNAL_FAMILIES if sig.get(f))
    vec.append(min(n_on, 6) / 6.0)
    for k in _EXTRA_PATTERNS:
        vec.append(1.0 if _EXTRA_RE[k].search(combined) else 0.0)
    return np.asarray(vec, dtype=np.float32)
