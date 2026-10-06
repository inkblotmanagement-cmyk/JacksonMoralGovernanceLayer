"""Jackson Moral Governance Layer (JMGL) v0.1.

An offline, deterministic rule-and-signal policy evaluator. No randomness,
no network calls by default. See README for scope and limitations.
"""
from .engine import evaluate_action, Verdict, ENGINE_VERSION

__all__ = ["evaluate_action", "Verdict", "ENGINE_VERSION"]
