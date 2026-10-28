"""Core logic for audio_intent (c2ct audio pipeline, MOSAIC local port).

Analyses the transcribed text produced by the transcription stage and
determines the spoken command's intent using purely statistical / lexical
methods. No external dependencies — pure Python.

Intent is represented as a triple (action, object, location) plus a single
``detected_command`` label. See the c2ct thesis for the scoring model.
"""

import math
import re
from collections import Counter
from typing import Any

# ── Vocabulary and intent definitions ──────────────────────────────────────────
_STOP_WORDS = {
    "the", "a", "an", "is", "are", "was", "were", "please",
    "can", "could", "would", "will", "shall", "should", "may",
    "might", "do", "does", "did", "be", "been", "being",
    "to", "of", "in", "at", "for", "with", "by",
    "and", "or", "but", "so", "yet", "nor",
    "it", "its", "this", "that", "these", "those",
    "i", "me", "my", "we", "our", "you", "your",
    "he", "him", "his", "she", "her", "they", "them", "their",
}

_ACTION_KEYWORDS: dict[str, list[str]] = {
    "activate":   ["turn on", "switch on", "put on", "activate", "start", "play",
                   "resume", "enable", "open", "launch", "on"],
    "deactivate": ["turn off", "switch off", "shut off", "deactivate", "stop",
                   "disable", "close", "kill", "off"],
    "increase":   ["turn up", "increase", "raise", "higher", "louder", "more",
                   "up", "boost", "amplify"],
    "decrease":   ["turn down", "decrease", "lower", "quieter", "reduce",
                   "down", "soften", "less"],
    "change":     ["change", "switch", "set", "adjust", "modify", "select",
                   "choose", "update"],
    "bring":      ["bring", "fetch", "get", "take", "move", "carry"],
}

_OBJECT_KEYWORDS: dict[str, list[str]] = {
    "lights":     ["light", "lights", "lamp", "lamps", "illumination",
                   "brightness", "bulb"],
    "music":      ["music", "song", "songs", "playlist", "radio", "audio",
                   "track", "sound"],
    "heat":       ["heat", "temperature", "thermostat", "heating", "warmth",
                   "warm", "hot", "cold"],
    "volume":     ["volume", "sound", "noise", "loud", "quiet", "mute"],
    "tv":         ["tv", "television", "screen", "display", "monitor"],
    "none":       [],
}

_LOCATION_KEYWORDS: dict[str, list[str]] = {
    "bedroom":    ["bedroom", "bed room", "sleeping room"],
    "kitchen":    ["kitchen"],
    "washroom":   ["washroom", "bathroom", "bath", "toilet"],
    "none":       [],
}

_COMMAND_WORDS = {
    "yes", "no", "up", "down", "left", "right",
    "on", "off", "stop", "go",
    "zero", "one", "two", "three", "four",
    "five", "six", "seven", "eight", "nine",
    "bed", "bird", "cat", "dog", "happy",
    "house", "marvin", "sheila", "tree", "wow",
}

# ── Scoring constants ───────────────────────────────────────────────────────────
_SCORE_PHRASE_EXACT = 3.0
_SCORE_PHRASE_ANY_ORDER = 1.5
_SCORE_WORD_EXACT = 1.0

_WEIGHT_KW = 0.7
_WEIGHT_COS = 0.3

_MAX_SCORE_ACTION = 4.0
_MAX_SCORE_OBJECT = 3.0
_MAX_SCORE_LOCATION = 2.0

_CONF_WEIGHT_ACTION = 0.5
_CONF_WEIGHT_OBJECT = 0.35
_CONF_WEIGHT_LOCATION = 0.15
_TOTAL_INTENTS = len(_ACTION_KEYWORDS) + len(_OBJECT_KEYWORDS) + len(_LOCATION_KEYWORDS)

_WORD_RE = re.compile(r"[a-z]+(?:[-'][a-z]+)*")


def _tokenise(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


def _remove_stopwords(tokens: list[str]) -> list[str]:
    return [t for t in tokens if t not in _STOP_WORDS]


def _keyword_score(tokens: list[str], text_lower: str,
                   keyword_map: dict[str, list[str]]) -> dict[str, float]:
    token_set = set(tokens)
    scores: dict[str, float] = {label: 0.0 for label in keyword_map}
    for label, keywords in keyword_map.items():
        for kw in keywords:
            if " " in kw:
                if kw in text_lower:
                    scores[label] += _SCORE_PHRASE_EXACT
                elif all(w in token_set for w in kw.split()):
                    scores[label] += _SCORE_PHRASE_ANY_ORDER
            else:
                if kw in token_set:
                    scores[label] += _SCORE_WORD_EXACT
    return scores


def _cosine_score(query_vec: Counter,
                  keyword_map: dict[str, list[str]]) -> dict[str, float]:
    scores: dict[str, float] = {}
    q_norm = math.sqrt(sum(v * v for v in query_vec.values()))
    if q_norm == 0:
        return {label: 0.0 for label in keyword_map}
    for label, keywords in keyword_map.items():
        centroid: Counter = Counter()
        for kw in keywords:
            for tok in _tokenise(kw):
                centroid[tok] += 1.0
        c_norm = math.sqrt(sum(v * v for v in centroid.values()))
        if c_norm == 0:
            scores[label] = 0.0
            continue
        dot = sum(query_vec.get(t, 0) * centroid.get(t, 0) for t in centroid)
        scores[label] = dot / (q_norm * c_norm)
    return scores


def _best_label(keyword_scores: dict[str, float],
                cosine_scores: dict[str, float]) -> tuple[str, float]:
    labels = list(keyword_scores.keys())
    fused = {
        label: _WEIGHT_KW * keyword_scores[label] + _WEIGHT_COS * cosine_scores.get(label, 0.0)
        for label in labels
    }
    best = max(fused, key=lambda l: fused[l])
    return best, round(fused[best], 4)


def _normalise_confidence(raw_score: float, max_possible: float = 10.0) -> float:
    return round(min(raw_score / max_possible, 1.0), 4)


def classify_intent(payload: dict) -> dict:
    """Classify the spoken command intent from ``transcribed_text``."""
    result: dict[str, Any] = dict(payload)

    text: str = str(payload.get("transcribed_text", "")).strip()
    text_lower = text.lower()

    tokens = _tokenise(text_lower)
    content_tokens = _remove_stopwords(tokens)
    query_vec: Counter = Counter(content_tokens)

    detected_command = "unknown"
    if len(content_tokens) == 1 and content_tokens[0] in _COMMAND_WORDS:
        detected_command = content_tokens[0]
    elif tokens and tokens[0] in _COMMAND_WORDS:
        detected_command = tokens[0]

    action_kw = _keyword_score(content_tokens, text_lower, _ACTION_KEYWORDS)
    action_cos = _cosine_score(query_vec, _ACTION_KEYWORDS)
    best_action, action_raw = _best_label(action_kw, action_cos)
    action_conf = _normalise_confidence(action_raw, max_possible=_MAX_SCORE_ACTION)

    object_kw = _keyword_score(content_tokens, text_lower, _OBJECT_KEYWORDS)
    object_cos = _cosine_score(query_vec, _OBJECT_KEYWORDS)
    best_object, object_raw = _best_label(object_kw, object_cos)
    if object_raw < 0.01:
        best_object = "none"
    object_conf = _normalise_confidence(object_raw, max_possible=_MAX_SCORE_OBJECT)

    location_kw = _keyword_score(content_tokens, text_lower, _LOCATION_KEYWORDS)
    location_cos = _cosine_score(query_vec, _LOCATION_KEYWORDS)
    best_location, location_raw = _best_label(location_kw, location_cos)
    if location_raw < 0.01:
        best_location = "none"
    location_conf = _normalise_confidence(location_raw, max_possible=_MAX_SCORE_LOCATION)

    intent_confidence = round(
        _CONF_WEIGHT_ACTION * action_conf
        + _CONF_WEIGHT_OBJECT * object_conf
        + _CONF_WEIGHT_LOCATION * location_conf,
        4,
    )

    result.update({
        "detected_command":  detected_command,
        "intent_action":     best_action,
        "intent_object":     best_object,
        "intent_location":   best_location,
        "intent_confidence": intent_confidence,
    })
    return result
