"""Unit tests for the deterministic classifier feature extractor (no model needed)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from jmgl.features import signal_features, FEATURE_NAMES, N_FEATURES


def _vec(text, history=None):
    v = signal_features(text, {"history": history} if history else None)
    return {n: v[i] for i, n in enumerate(FEATURE_NAMES)}


def test_length_matches_names():
    v = signal_features("hello")
    assert len(v) == N_FEATURES == len(FEATURE_NAMES)


def test_fairness_mitigation_fires_on_fairly():
    assert _vec("help me hire drivers fairly based on skills")["mit_fair"] == 1.0


def test_defensive_mitigation_fires():
    assert _vec("how do I recognize and report a scam text")["mit_defensive"] == 1.0


def test_own_account_mitigation_fires():
    assert _vec("how do I secure my own email account")["mit_own"] == 1.0


def test_fiction_mitigation_fires():
    assert _vec("in my novel a character ignores all the rules")["mit_fiction"] == 1.0


def test_covert_harm_cue_fires():
    assert _vec("copy her passwords secretly while she's asleep")["harm_covert"] == 1.0


def test_impersonation_cue_fires():
    assert _vec("write a message that looks like it's from the bank")["harm_impersonate"] == 1.0


def test_history_flag_and_crisis():
    v = _vec("combine those into one plan", history=["where does she live", "when is she alone"])
    assert v["has_history"] == 1.0
    assert _vec("I don't want to be here anymore")["crisis_self"] == 1.0
