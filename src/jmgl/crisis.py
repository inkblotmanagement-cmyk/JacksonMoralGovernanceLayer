"""JL-08 self-harm / crisis cue families (v0.1.1).

Families follow commonly published suicide warning-sign categories
(expressing a wish to die or not exist, feeling like a burden, hopelessness /
no reason to live, unbearable pain, and preparatory behaviour such as giving
away possessions or saying goodbye). Still English regex; still brittle.

Scoring (deterministic):
  strong cue (first-person)            -> ESCALATE
  weak cue + another weak/emotion cue  -> ESCALATE   (bias toward escalation)
  weak cue with a global object         -> ESCALATE   ("everything", "it all", "life")
  weak cue inside a situational frame   -> no escalation ("this week", "this meeting", "printer")
  fiction/writing frame, no first-person strong cue -> no escalation
  third-party concern ("my friend says she doesn't want to be here") -> ESCALATE
       with supporter-oriented resources
"""
from __future__ import annotations

import re

FLAGS = re.IGNORECASE

WISH_NOT_EXIST = [
    r"\b(?:don'?t|do not|no longer) (?:want|wanna) to (?:exist|be alive|live|be here|wake up|be around)\b",
    r"\bwish(?:ing|ed)? (?:i|that i) (?:was|were|had|could) (?:be )?(?:dead|gone|never been born|not born|disappear\w*|vanish\w*)\b",
    r"\b(?:hope|wish|pray) (?:i|that i) (?:don'?t|won'?t|never|do not) wake up\b",
    r"\b(?:not|never) (?:to )?wake up (?:again|tomorrow|in the morning)?\b",
    r"\bwant(?:s|ed)? to (?:die|be dead|stop existing|cease to exist|not exist)\b",
    r"\btired of (?:existing|living|being alive|life|being here)\b",
    r"\b(?:kill|end) (?:myself|my life)\b", r"\bsuicid", r"\bhurt(?:ing)? myself\b", r"\bself[- ]harm",
]
BURDEN = [
    r"\bbetter off without me\b",
    r"\b(?:world|everyone|everybody|they|family|people) (?:would|'?d) be (?:better|lighter|happier|relieved|fine)\b.*\b(?:without me|if i (?:was|were|wasn'?t|weren'?t)|gone)\b",
    r"\b(?:i'?m|i am) (?:just )?(?:a|such a) burden\b", r"\bburden (?:to|on) (?:everyone|my family|them|people)\b",
    r"\b(?:relieved|happier|better) if i (?:was|were) gone\b", r"\bif i (?:wasn'?t|weren'?t) (?:here|in it|around|alive)\b",
    r"\bnobody would (?:notice|care|miss me)\b", r"\b(?:happier|better off|relieved|lighter|fine) if i (?:just )?(?:vanish\w*|disappear\w*|died|was gone|were gone|wasn\'?t here)\b", r"\bno one would (?:notice|care|miss me)\b",
]
HOPELESS = [
    r"\b(?:no|don'?t see (?:the|any)|there'?s no) (?:point|reason) (?:anymore|in (?:living|anything|going on|trying)|to (?:live|go on|keep going))\b",
    r"\bwhat'?s the point (?:of (?:living|life|anything|going on|being here)|anymore)\b",
    r"\bpoint of living\b",
    r"\bnothing (?:is )?(?:ever )?(?:going to|gonna|will ever) (?:get|be) better\b",
    r"\bno (?:way out|hope left|future for me)\b", r"\bcan'?t (?:go on|keep going|take (?:it|this) anymore|do this anymore)\b",
]
PAIN_PERMANENT = [
    r"\b(?:pain|hurt|suffering)\b.*\b(?:go away|stop|end)\b.*\b(?:permanently|forever|for good)\b",
    r"\b(?:end|stop) (?:it all|everything|things) (?:for good|permanently|forever)\b",
]
PREPARATORY = [
    r"\bgiving away (?:all )?my (?:things|stuff|belongings|possessions)\b",
    r"\b(?:writing|wrote|written) (?:goodbye|farewell|suicide) (?:letters?|notes?)\b",
    r"\bgoodbye (?:letters?|notes?)\b", r"\bsaying (?:my )?goodbyes? to everyone\b",
]
# Weak / ambiguous cues: escalate only in combination or with a global object.
WEAK = [
    r"\bwant (?:it|this|everything|it all|all of this|things) to (?:stop|end)\b",
    r"\b(?:disappear\w*|vanish\w*|fade away|be gone)\b", r"\bdone trying\b", r"\bgive up\b",
    r"\bcan'?t do this\b", r"\bexhausted (?:by|of) (?:everything|life)\b",
]
EMOTION = [r"\b(?:empty|numb|hopeless|worthless|alone|trapped|broken|unbearable)\b", r"\bin (?:so much )?pain\b"]
GLOBAL_OBJECT = [r"\b(?:everything|it all|all of (?:it|this)|my life|life|myself|everyone)\b"]
SITUATIONAL = [
    r"\bthis (?:week|meeting|class|shift|day|semester|project|job|traffic|noise|printer|app)\b",
    r"\b(?:printer|battery|phone|laptop|app|computer|social media|a nap|nap|vacation|weekend|inbox)\b",
    r"\bto focus\b", r"\bfor a (?:week|month|while|bit)\b",
]
FICTION = [r"\b(?:novel|story|screenplay|script|poem|character|fiction|book i'?m writing)\b", r"\bportray\b"]
THIRD_PARTY = [
    r"\bmy (?:friend|sister|brother|son|daughter|partner|wife|husband|mom|dad|mother|father|coworker|student|roommate)\b.*\b(?:says?|said|keeps saying|talks? about|told me|mentioned)\b",
    r"\bhow (?:can|do) i (?:support|help)\b",
]
SUPPORTER_RESOURCES = [
    "US: the 988 Suicide & Crisis Lifeline (call/text 988, chat 988lifeline.org) also helps people worried about someone else",
    "If they may be in immediate danger, call 911 (US) or your local emergency number",
    "Stay with them, listen without judgment, and ask directly whether they are thinking about suicide",
]


def _m(text, pats):
    return [p for p in pats if re.search(p, text, FLAGS)]


def assess(text: str) -> dict:
    """Return {'level': 'none'|'self'|'third_party', 'cues': {...}}."""
    cues = {
        "wish_not_exist": _m(text, WISH_NOT_EXIST), "burden": _m(text, BURDEN), "hopeless": _m(text, HOPELESS),
        "pain_permanent": _m(text, PAIN_PERMANENT), "preparatory": _m(text, PREPARATORY), "weak": _m(text, WEAK),
        "emotion": _m(text, EMOTION), "global": _m(text, GLOBAL_OBJECT), "situational": _m(text, SITUATIONAL),
        "fiction": _m(text, FICTION), "third_party": _m(text, THIRD_PARTY),
    }
    strong = any(cues[k] for k in ("wish_not_exist", "burden", "hopeless", "pain_permanent", "preparatory"))
    weak_hit = bool(cues["weak"])
    third = bool(cues["third_party"])

    if cues["fiction"] and not third and not re.search(r"\bi (?:feel|am|'m|want|wish|hope)\b", text, FLAGS):
        return {"level": "none", "cues": cues}
    if third and (strong or weak_hit):
        return {"level": "third_party", "cues": cues}
    if strong:
        return {"level": "self", "cues": cues}
    if weak_hit:
        # A situational frame (a week, a meeting, a device, a break) anchors weak
        # cues to a thing rather than to life itself; strong cues still escalate.
        if cues["situational"]:
            return {"level": "none", "cues": cues}
        if len(cues["weak"]) >= 2 or cues["emotion"] or cues["global"]:
            return {"level": "self", "cues": cues}
    return {"level": "none", "cues": cues}
