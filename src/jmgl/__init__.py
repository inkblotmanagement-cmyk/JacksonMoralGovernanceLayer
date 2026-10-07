"""Jackson Moral Governance Layer (JMGL).

v0.1 rule engine: an offline, deterministic rule-and-signal policy evaluator with
no third-party dependencies.

v0.4 ensemble (optional): rules + a learned category classifier. It needs numpy
(+ fastembed / scikit-learn for the model), so it is imported lazily: plain
`from jmgl import evaluate_action` keeps working with no extra dependencies, and
`evaluate_action_ensemble` / `ENSEMBLE_VERSION` are resolved on first access.
"""
from .engine import evaluate_action, Verdict, ENGINE_VERSION

__all__ = ["evaluate_action", "evaluate_action_ensemble", "evaluate_grace_force",
           "Verdict", "ENGINE_VERSION", "ENSEMBLE_VERSION", "GRACE_VERSION"]


def __getattr__(name):
    if name in ("evaluate_action_ensemble", "ENSEMBLE_VERSION"):
        from . import ensemble
        return getattr(ensemble, name)
    if name in ("evaluate_grace_force", "GRACE_VERSION"):
        from . import grace
        return getattr(grace, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
