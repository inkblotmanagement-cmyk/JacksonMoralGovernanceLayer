"""Locate JMGL data files in a source checkout *and* in an installed wheel.

Resolution order (first existing path wins):
  1. An explicit environment variable (JMGL_LAWS_PATH, JMGL_GRACE_CONFIG_PATH,
     JMGL_JUDGE_SCHEMA_PATH, JMGL_MODEL_DIR).
  2. The repository layout (spec/laws.json, eval/model/...), used by a git checkout
     or an editable install.
  3. Package data bundled into the wheel under jmgl/data/ (see pyproject.toml).
"""
from __future__ import annotations

import os
from pathlib import Path

_PKG_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _PKG_DIR.parents[1]
_DATA_DIR = _PKG_DIR / "data"


def _first(env: str, *candidates: Path) -> Path:
    override = os.environ.get(env)
    if override:
        return Path(override)
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


def laws_path() -> Path:
    return _first("JMGL_LAWS_PATH", _REPO_ROOT / "spec" / "laws.json", _DATA_DIR / "laws.json")


def grace_config_path() -> Path:
    return _first("JMGL_GRACE_CONFIG_PATH", _REPO_ROOT / "spec" / "grace_force.json",
                  _DATA_DIR / "grace_force.json")


def judge_schema_path() -> Path:
    return _first("JMGL_JUDGE_SCHEMA_PATH", _REPO_ROOT / "spec" / "judge_schema.json",
                  _DATA_DIR / "judge_schema.json")


def model_dir() -> Path:
    override = os.environ.get("JMGL_MODEL_DIR")
    if override:
        return Path(override)
    for c in (_REPO_ROOT / "eval" / "model", _DATA_DIR / "model"):
        if (c / "clf.npz").exists():
            return c
    return _REPO_ROOT / "eval" / "model"
