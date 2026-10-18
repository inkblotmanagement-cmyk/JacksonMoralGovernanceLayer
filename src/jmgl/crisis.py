"""JL-08 self-harm / crisis cue families (v0.1.2: + lethal-means / overdose family).

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
    r"\b(?:don'?t|do not|does not|doesn'?t|no longer) (?:want|wanna|wants) to (?:exist|be alive|live|be here|wake up|be around)\b",
    r"\bwish(?:ing|ed)? (?:i|that i) (?:was|were|had|could) (?:be )?(?:dead|gone|never been born|not born|disappear\w*|vanish\w*)\b",
    r"\b(?:hope|wish|pray) (?:i|that i) (?:just |really |simply |honestly |somehow |could )*(?:don'?t|won'?t|never|do not|dont) wake up\b(?! (?:early|late|groggy|tired|on time|in time|during|at night|in the night|before|feeling|with|for|at \d))",
    r"\b(?:not|never) (?:to )?wake up(?: again| tomorrow| in the morning)?\b(?! (?:early|late|groggy|tired|on time|in time|during|at night|in the night|before|feeling|with|for))",
    r"\bwant(?:s|ed)? to (?:die|be dead|stop existing|cease to exist|not exist)\b",
    r"\btired of (?:existing|living|being alive|life|being here)\b",
    r"\bplan(?:ning|s|ned)? to (?:end|finish) (?:it all|things|my life|everything|it)\b",
    r"\bend (?:it all|things|my life|everything) (?:this|tonight|tomorrow|soon|for good|permanently|before|over the)\b",
    r"\b(?:kill|end) (?:myself|my life)\b", r"\bsuicid", r"\bhurt(?:ing)? myself\b", r"\bself[- ]harm",
]
BURDEN = [
    r"\b(?:everyone|everybody|the world|they|people|we|his family|her family|his|her|their family) (?:would|'?d|'?ll|will) be (?:better off|better|happier|fine|lighter) without (?:him|her|them)\b",
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
    r"\bwho (?:should|will|'?ll|would) (?:get|have) my (?:things|stuff|belongings|possessions|guitar|cat|dog|books?|car|house|savings|\w+)\b",
    r"\b(?:settle|settled|sort(?:ed)?|in order|figure out who gets|decide who gets)\b[^.?!]*\bbefore i (?:go|'?m gone|leave|die|am gone)\b",
    r"\bget my affairs in order\b",
]
# Means-seeking: asking for a lethal amount / method of overdose. This is high risk
# regardless of framing, so it is checked BEFORE the fiction exemption and is not
# lifted by joke/hedge framing ("just joking", "lol", "asking for a friend",
# "hypothetically", "for a story"). Benign dosing questions ("max safe dose of
# tylenol for a headache", "ibuprofen with coffee") have no lethal outcome and
# do not match.
_MED = (r"(?:pills?|tablets?|capsules?|meds|medications?|medicine|prescriptions?|painkillers?|pain killers?|"
        r"sleeping pills?|sleep(?:ing)? meds|sleep aids?|tylenol|acetaminophen|paracetamol|panadol|ibuprofen|advil|"
        r"motrin|aleve|naproxen|aspirin|excedrin|benadryl|diphenhydramine|nyquil|zzzquil|unisom|doxylamine|"
        r"melatonin|ambien|zolpidem|xanax|alprazolam|valium|diazepam|klonopin|clonazepam|ativan|lorazepam|benzos?|"
        r"oxy(?:codone|contin)?|percocet|vicodin|hydrocodone|tramadol|codeine|morphine|fentanyl|methadone|heroin|"
        r"insulin|antidepressants?|sertraline|zoloft|prozac|fluoxetine|lexapro|citalopram|amitriptyline|lithium|"
        r"seroquel|quetiapine|gabapentin|propranolol|digoxin|iron pills?|antifreeze|bleach|rat poison)")
_QTY = r"(?:how (?:many|much)|what (?:dose|amount|number|quantity)|which dose|enough|amount of|number of|dose of|bottle of|the whole bottle|a whole bottle|all (?:of )?my)"
_OUTCOME = (r"(?:(?:to |and |i'?d |i would |would i |i'?ll |i will |will i |do i |before i |till i |until i |so i )(?:just )?die\b|"
            r"kills? (?:me|myself|yourself|a person|someone|an adult|a human)\b|"
            r"end (?:it|it all|my life|things|everything)\b|"
            r"(?:not|never) (?:to )?wake up\b(?! (?:early|late|groggy|tired|on time|in time|during|at night|feeling|with))|"
            r"stops? (?:my|your|the|a person'?s|someone'?s) heart\b|be (?:fatal|deadly|lethal)\b|"
            r"(?:to |and )(?:od|overdose)\b|be dead\b)")
LETHAL_MEANS = [
    # "lethal / fatal / deadly dose|amount" (incl. "overdose amount")
    r"\b(?:lethal|fatal|deadly|killing|toxic enough|overdose) (?:dose|dosage|amount|quantity|number|level|limit)\b",
    r"\bdose (?:that|which|it takes to|needed to|required to) (?:would |will |could )?(?:kill|be fatal|be lethal|end)\b",
    # quantity-seeking + medication + death outcome, within one sentence (either order)
    _QTY + r"\b[^.?!]{0,60}\b" + _MED + r"\b[^.?!]{0,70}" + _OUTCOME,
    _MED + r"\b[^.?!]{0,60}\b" + _QTY + r"\b[^.?!]{0,60}" + _OUTCOME,
    _OUTCOME + r"[^.?!]{0,40}\b" + _QTY + r"\b[^.?!]{0,40}\b" + _MED + r"\b",
    # medication + an explicit self-directed death outcome, no quantity word needed
    # ("is it safe to take 40 tylenol at once to end it", "sleeping pills so i never wake up")
    _MED + r"\b[^.?!]{0,50}\b(?:to|and|so|then|until|till)\s+(?:i\s+)?(?:can\s+|could\s+|would\s+|will\s+)?(?:just\s+)?(?:die\b|end it\b|end it all\b|end my life\b|end everything\b|kill myself\b|(?:not|never) wake up\b(?! (?:early|late|groggy|tired|on time|in time|during|at night|feeling|with|at \d)))",
    # a large count of a medication + "would I die / not wake up" ("what if I took 30 benadryl, would I die")
    r"\b(?:\d{2,}|dozens? of|a (?:bunch|handful|lot) of|twenty|thirty|forty|fifty|a hundred)\s+(?:\w+\s+){0,2}?" + _MED + r"\b[^.?!]{0,60}[.?!,]?\s*(?:would|will|could|do|am|might) i (?:die|be dead|not wake up|never wake up|stop breathing)\b",
    # "how many pills to die" / "how many to end it"
    r"\bhow (?:many|much)\b[^.?!]{0,40}\b(?:to|would it take to|does it take to|until i|before i|till i|and i'?d)\s+(?:just )?(?:die|end it|end it all|not wake up|never wake up|kill myself|od|overdose)\b",
    # OD / overdose on purpose
    r"\b(?:od|o\.d\.|overdose)\b[^.?!]{0,30}\b(?:on purpose|intentionally|deliberately|purposely|for real this time)\b",
    r"\b(?:on purpose|intentionally|deliberately)\b[^.?!]{0,15}\b(?:od|o\.d\.|overdose)\b",
    r"\b(?:i(?:'m| am)? (?:going|gonna|planning|about|ready|want|wanna|trying)|i'?ll|i will|how (?:do|would|could|can|should) i|how to|best way to|easiest way to|painless(?:ly)?(?: way)? to)\s+(?:to\s+)?(?:just )?(?:od|o\.d\.|overdose)\b",
    r"\b(?:take|took|taking|takes|swallow\w*|down|downed|chug\w*|eat|ate)\s+(?:the |a |an |my |her |his )?(?:whole|entire) (?:bottle|pack|box|packet|blister pack)\b",
    r"\b(?:take|took|taking|swallow\w*|down|downed|chug\w*)\s+all (?:of )?(?:my|the|these|those) " + _MED + r"\b",
    r"\bmost painless way to\b[^.?!]{0,30}\b(?:die|go|end it|od|overdose)\b",
]
# Benign medication-safety information (safe dosing, interactions, storage, overdose
# recognition / reversal). Used by Grace Force ONLY to skip the low-confidence
# route when there is no self-harm cue at all; it never overrides a crisis cue.
MED_SAFETY_INFO = [
    _MED + r"\b[^.?!]{0,60}\b(?:safe(?:ly)?|max(?:imum)?|recommended|daily limit|per day|a day|interact\w*|together|with (?:a |an )?(?:glass of |cup of |can of )?(?:coffee|alcohol|wine|beer|food|milk|caffeine|juice|grapefruit|soda)|side effects?|stor(?:e|ing|age)|expired?|while (?:pregnant|breastfeeding))\b",
    r"\b(?:safe(?:ly)?|max(?:imum)?|recommended|interact\w*|side effects?|how (?:do i|to|should i) stor\w*)\b[^.?!]{0,60}\b" + _MED + r"\b",
    r"\b(?:signs? of|symptoms? of|recogni[sz]e|reverse|treat(?:ing)?|respond to|prevent(?:ing)?)\b[^.?!]{0,30}\b(?:an? )?(?:opioid |accidental )?(?:overdose|od)\b",
    r"\b(?:naloxone|narcan)\b",
    r"\b(?:accidental(?:ly)?|by accident|by mistake|poison control|double(?:d)? (?:up|dose))\b[^.?!]{0,40}\b" + _MED + r"\b",
    r"\b(?:accidental(?:ly)?|by accident|by mistake)\b[^.?!]{0,40}\b(?:two|2|double|extra) dos(?:e|es|ing)\b",
    r"\bhow (?:much|many)\b[^.?!]{0,30}\b" + _MED + r"\b[^.?!]{0,20}\b(?:should|can|could|do) (?:i|you|we|my \w+) (?:take|give|have)\b",
]

# Accidental-exposure / poison-control questions are urgent but not self-harm.
ACCIDENTAL = [
    r"\b(?:my|our|a) (?:dog|cat|puppy|kitten|pet|kid|child|son|daughter|toddler|baby|grandma|grandpa)\b[^.?!]{0,40}\b(?:ate|swallowed|got into|chewed|took|licked|drank|found and)\b",
    r"\b(?:accidental(?:ly)?|by accident|poison control|by mistake)\b",
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
    r"\b(?:my|a|an|our|the|one of my|this) (?:friend|sister|brother|son|daughter|partner|wife|husband|mom|dad|mother|father|coworker|student|roommate|ex|classmate|neighbou?r)\b.*\b(?:says?|said|keeps saying|talks? about|told me|mentioned|wrote|texted|messaged|posted|admitted|confessed|keeps talking)\b",
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
        "lethal_means": _m(text, LETHAL_MEANS), "accidental": _m(text, ACCIDENTAL),
    }
    strong = any(cues[k] for k in ("wish_not_exist", "burden", "hopeless", "pain_permanent", "preparatory"))
    weak_hit = bool(cues["weak"])
    third = bool(cues["third_party"])

    # Means-seeking for a lethal overdose: escalate regardless of joke / hedge /
    # fiction framing (fail closed). Accidental-exposure questions are exempt
    # unless another strong self-harm cue is also present.
    if cues["lethal_means"] and not (cues["accidental"] and not strong):
        return {"level": "third_party" if third else "self", "cues": cues}
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
