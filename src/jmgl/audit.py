"""Append-only JSONL audit log for JMGL."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_audit(path, request: str, verdict, laws_path, engine_version: str, *, log_raw: bool = False) -> dict:
    record = {
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "input_sha256": sha256_text(request),
        "decision": verdict.decision,
        "rule_id": verdict.rule_id,
        "engine_version": engine_version,
        "laws_sha256": sha256_file(laws_path),
    }
    if log_raw:
        record["input_raw"] = request
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # 'a' mode = append-only; each record is a single line.
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    return record
