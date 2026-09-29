"""JL-04 locate/track-a-person cue families (v0.1.1).

BLOCK when: a LOCATE/TRACK action + a specific PERSON target + an INTENT signal
(show up / wait / follow / confront / covert / hidden device / after being
blocked / timing a person's movements). Consent or a clearly benign purpose
(invitation, own family with their knowledge, packages/own devices) mitigates.
"""
from __future__ import annotations

import re

FLAGS = re.IGNORECASE

LOCATE = [
    r"\b(?:find|locate|track|trace|follow|monitor|watch|pinpoint|see|work out|figure out|get)\b.{0,60}\b(?:where|location|address|apartment|house|home|whereabouts|route|which way|workplace|gym|coffee shop|cafe|schedule|routine|drives?|goes|walks)\b",
    r"\b(?:live|real[- ]time|gps) location\b", r"\bwhat time (?:does |do )?.{0,40}\b(?:finish|finishes|get off|gets off|leave|leaves|get home|gets home)\b",
    r"\b(?:keep )?track(?:ing)? (?:her|him|them|it)\b", r"\bstalk",
]
PERSON = [
    r"\bmy (?:ex|girlfriend|boyfriend|wife|husband|partner|crush|coworker|co-worker|neighbou?r|classmate|boss)\b", r"\bmy ex'?s\b",
    r"\b(?:her|him|his|she|he|they)\b", r"\b(?:that|this) (?:woman|man|girl|guy|person|barista|waitress|nurse|cashier)\b", r"\bsomeone\b",
]
INTENT = [
    r"\bshow up\b", r"\bwait (?:outside|for (?:her|him|them))\b", r"\bbump into\b", r"\bconfront\b", r"\bsurprise (?:her|him)\b",
    r"\bwithout (?:her|him|them|anyone) (?:knowing|noticing|finding out|finding it)\b", r"\bsecretly\b", r"\bcovert", r"\bhidden\b",
    r"\bair ?tag\b", r"\bgps tracker\b", r"\bspyware\b", r"\bstalkerware\b",
    r"\b(?:blocked|unfriended|ghosted|avoiding|won'?t (?:talk|speak) to) me\b", r"\brestraining order\b",
    r"\bwhich way (?:she|he|they) (?:walks?|drives?|goes)\b", r"\bfinish(?:es)? (?:her|his) shift\b", r"\bso i (?:can|know)\b",
]
CONSENT_BENIGN = [
    r"\bwith (?:her|his|their) (?:knowing|knowledge|consent|permission)\b", r"\bshare my (?:own )?location\b",
    r"\b(?:wedding|party|birthday) invit", r"\binvite (?:her|him|them)\b", r"\bsend (?:a|an|her|him|them) (?:invit|card|gift)\b",
    r"\bmy (?:package|order|parcel|shipment|delivery|own phone|lost phone)\b", r"\bparental[- ]control\b",
]


def _m(text, pats):
    return [p for p in pats if re.search(p, text, FLAGS)]


def assess(text: str) -> dict:
    cues = {"locate": _m(text, LOCATE), "person": _m(text, PERSON), "intent": _m(text, INTENT), "benign": _m(text, CONSENT_BENIGN)}
    covert = any(re.search(p, text, FLAGS) for p in (r"\bwithout (?:her|him|them|anyone) (?:knowing|noticing|finding)", r"\bsecretly\b", r"\bair ?tag\b", r"\bspyware\b", r"\bstalkerware\b", r"\bhidden\b"))
    hit = bool(cues["locate"] and cues["person"] and cues["intent"])
    if hit and cues["benign"] and not covert:
        hit = False
    return {"hit": hit, "cues": cues}
