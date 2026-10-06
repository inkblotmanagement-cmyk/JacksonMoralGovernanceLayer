"""Lexical/intent signal extraction for JMGL v0.1.

Transparent, deterministic regex "signal families" over English text. This is
NOT a language model and it does not understand meaning; it detects cues that
the engine combines into an intent judgement (purpose + domain + who is harmed
+ mitigating framing). It is brittle to paraphrase (see README).

Leakage policy: patterns here were derived from the MAIN test-case descriptions
plus ordinary dictionary synonyms. Scenario-specific phrasings that appear only
in tests/heldout.json were deliberately excluded so the held-out score is not
inflated. (The held-out set and these rules share an author, so some leakage of
intuition is unavoidable; see README.)
"""
from __future__ import annotations

import re
from typing import Iterable


def _any(text: str, patterns: Iterable[str]) -> list[str]:
    return [p for p in patterns if re.search(p, text, flags=re.IGNORECASE)]


# --- request to PRODUCE an artifact / carry out an action --------------------
PRODUCE = [
    r"\b(?:write|draft|make|create|generate|compose|craft|design|build|set up|give me|send|put together|help me (?:write|make|draft|create|set up|get|copy|find|track))\b",
    r"\bhow (?:do|can|would) i\b", r"\bhelp me\b", r"\bi (?:want|need) to\b", r"\bi'?m going to\b",
]

# --- purpose / intent signals -------------------------------------------------
DECEIVE = [
    r"\bdisguis", r"\bpretend(?:ing)? to be\b", r"\bimpersonat", r"\bpose as\b",
    r"\bfake\b", r"\bspoof", r"\bmasquerad", r"\bmislead", r"\btrick (?:them|people|him|her|customers|users)\b",
    r"\blooks? (?:like it(?:'s| is)? )?(?:from|official|legit)", r"\bso (?:they|people|customers|victims?) (?:think|believe)\b",
]
PRESSURE = [
    r"\bpressur", r"\bcoerc", r"\bmanipulat", r"\bguilt[- ]trip", r"\bconvince (?:her|him|them|my)\b",
    r"\bpush (?:her|him|them|my)\b.*\b(?:to|into)\b", r"\bpersuade (?:her|him|them|my)\b", r"\bscare (?:her|him|them)\b",
]
CONCEAL = [
    r"\bquietly\b", r"\bcovert(?:ly)?\b", r"\bsecretly\b", r"\bwithout (?:them|him|her|anyone|people) (?:knowing|noticing)\b",
    r"\bso (?:no one|nobody) (?:knows|notices|finds out)\b", r"\bhide (?:it|this|that)\b",
    r"\bwithout (?:his|her|their) (?:knowledge|consent|permission)\b",
]
TARGET_PERSON = [
    r"\bmy (?:ex|coworker|co-worker|colleague|roommate|neighbou?r|boss|wife|husband|girlfriend|boyfriend|classmate|friend)\b",
    r"\bsomeone\b", r"\ba (?:specific )?(?:person|woman|man|girl|guy)\b", r"\bthis (?:person|woman|man|girl|guy)\b",
    r"\b(?:her|his|their) (?:location|whereabouts|address|schedule|routine)\b",
]
BYPASS_AUTHORITY = [
    r"\bi (?:hereby )?authori[sz]e you to (?:skip|bypass|ignore|disable|turn off)\b",
    r"\b(?:skip|bypass|ignore|disable|turn off) (?:the |your )?(?:ethics?|safety|moral|governance) (?:check|filter|rules?|layer|review)s?\b",
    r"\byou have (?:my )?permission to (?:skip|bypass|ignore)\b", r"\bi(?:'m| am) (?:authori[sz]ed|allowed) to (?:bypass|skip|override)\b",
]
JAILBREAK = [
    r"\bpretend (?:that )?you (?:have|had) no (?:rules|restrictions|guidelines|limits|filters)\b",
    r"\b(?:you have|with) no (?:rules|restrictions|guidelines|limits|filters)\b",
    r"\bignore (?:all |your )?(?:previous|prior|earlier) instructions\b", r"\bjailbreak\b",
    r"\bwithout (?:any )?(?:rules|restrictions|guidelines|filters)\b", r"\bunfiltered\b",
]

# --- mitigating framing -------------------------------------------------------
EDU_DEFENSIVE = [
    r"\btrain(?:ing)? (?:my )?(?:staff|team|employees|coworkers|people)\b", r"\bteach (?:my )?(?:staff|team|employees|people|students|kids)\b",
    r"\bspot(?:ting)?\b", r"\brecogni[sz]e\b", r"\bdetect\b", r"\bidentify\b",
    r"\bprotect (?:my|myself|our|against)\b", r"\bdefend against\b", r"\bprevent(?:ing)?\b",
    r"\bhistory of\b", r"\bfor (?:awareness|education|research)\b", r"\bhow do(?:es)? .* (?:trick|fool|deceive|work)\b",
    r"\bsecur(?:e|ing) my\b", r"\bmy own\b", r"\blaws?\b",
]
VICTIM_PERSPECTIVE = [
    r"\b(?:tracking|following|stalking|harass(?:ing)?|monitoring|watching|scamming|threatening) (?:me|my)\b",
    r"\bwhat should i do if\b", r"\bi(?:'m| am) being (?:tracked|followed|stalked|harassed|scammed)\b",
    r"\bhappened to me\b", r"\bhow do i (?:stop|report|get away from)\b",
]
FAIRNESS = [r"\bfair\b", r"\binclusive\b", r"\bequal opportunity\b", r"\bbias[- ]free\b", r"\bnon-?discriminat"]

# --- domain signals -----------------------------------------------------------
PHISHING = [r"\bphish", r"\bbank (?:notice|alert|message|email)\b", r"\bverify your (?:account|identity)\b",
            r"\bclick (?:this|the) link\b", r"\baccount (?:has been )?(?:locked|suspended)\b"]
CREDENTIAL = [r"\bpasswords?\b", r"\bcredentials?\b", r"\blogins?\b", r"\bunlocked (?:laptop|computer|pc)\b"]
OTHER_PERSONS_ACCOUNT = [r"\b(?:coworker|co-worker|colleague|roommate|boss|someone else|another person|his|her|their)(?:'s)?\b.*\b(?:passwords?|credentials?|logins?|laptop|computer|accounts?)\b",
                         r"\bcopy(?:ing)?\b.*\bpasswords?\b", r"\bsteal"]
ELDER = [r"\belder(?:ly)?\b", r"\bseniors?\b", r"\baging (?:parent|mother|father)\b", r"\bgrand(?:mother|father|ma|pa)\b",
         r"\bsavings\b", r"\bretirement\b", r"\bpension\b", r"\bnest egg\b"]
STALK = [r"\bstalk", r"\bpublic posts\b", r"\btrack (?:her|him|them|someone)\b", r"\bmonitor (?:her|his|their|someone)\b",
         r"\b(?:find|figure out|work out) where (?:she|he|they|someone) (?:is|lives|goes|works)\b", r"\b(?:location|whereabouts|address|routine)\b"]
DISCRIM = [r"\bzip ?codes?\b", r"\bneighbou?rhoods?\b", r"\bpart of town\b", r"\bexclud", r"\bfilter out\b", r"\bscreen (?:out|them out)\b",
           r"\b(?:race|religion|ethnicity|national origin|disability|pregnan)"]
HIRING = [r"\bhir(?:e|ing)\b", r"\bapplicants?\b", r"\bcandidates?\b", r"\bjob\b", r"\brecruit", r"\bresum", r"\bscreening\b"]
MARKET = [r"\bpump\b", r"\bdump\b", r"\bfake accounts?\b", r"\bhype\b", r"\bshill", r"\bbefore (?:i|we) sell\b",
          r"\b(?:coin|token|crypto|stock)\b"]
MARKET_PLAN = [r"\bmy (?:coin|token|stock|crypto)\b", r"\bbefore (?:i|we) sell\b", r"\bthen (?:i|we) sell\b", r"\bfake accounts?\b", r"\bhype (?:up )?(?:my|our)\b"]
SELF_HARM = [r"\bkill myself\b", r"\bsuicid", r"\bend (?:my life|it all)\b", r"\bwant (?:everything|it all|it) to stop\b",
             r"\bcan'?t (?:go on|keep going|do this anymore)\b", r"\bdon'?t want to (?:be here|live|exist) anymore\b",
             r"\bhurt(?:ing)? myself\b", r"\bno reason to live\b"]
SENSITIVE_TOPIC = [r"\baddress\b", r"\bschedule\b", r"\bpasswords?\b", r"\bwhere .* lives\b", r"\bwhen .* (?:alone|leaves?|gets? off)\b"]


def scan(text: str) -> dict:
    groups = {
        "produce": PRODUCE, "deceive": DECEIVE, "pressure": PRESSURE, "conceal": CONCEAL,
        "target_person": TARGET_PERSON, "bypass_authority": BYPASS_AUTHORITY, "jailbreak": JAILBREAK,
        "edu_defensive": EDU_DEFENSIVE, "victim": VICTIM_PERSPECTIVE, "fairness": FAIRNESS, "phishing": PHISHING, "credential": CREDENTIAL,
        "other_account": OTHER_PERSONS_ACCOUNT, "elder": ELDER, "stalk": STALK, "discrim": DISCRIM,
        "hiring": HIRING, "market": MARKET, "market_plan": MARKET_PLAN, "self_harm": SELF_HARM,
        "sensitive": SENSITIVE_TOPIC,
    }
    return {k: _any(text, v) for k, v in groups.items()}
