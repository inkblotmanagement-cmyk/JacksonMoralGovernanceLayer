"""CLI: python -m jmgl "request text" [--history "turn1" --history "turn2"] [--json] [--audit PATH]"""
from __future__ import annotations

import argparse
import json
import sys
import textwrap

from .engine import evaluate_action, ENGINE_VERSION


def render(request: str, v, width: int = 78) -> str:
    lines = [f"> {l}" for l in textwrap.wrap(request, width - 2)]
    lines.append(f"  DECISION : {v.decision}")
    lines.append(f"  RULE     : {v.rule_id}")
    lines += textwrap.wrap(v.reason, width, initial_indent="  REASON   : ", subsequent_indent=" " * 13)
    if v.suggested_modification:
        lines += textwrap.wrap(v.suggested_modification, width, initial_indent="  INSTEAD  : ", subsequent_indent=" " * 13)
    for r in v.resources:
        lines += textwrap.wrap(r, width, initial_indent="  HELP     : ", subsequent_indent=" " * 13)
    return "\n".join(lines)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="jmgl", description=f"JMGL {ENGINE_VERSION} offline policy evaluator")
    p.add_argument("request")
    p.add_argument("--history", action="append", default=[])
    p.add_argument("--json", action="store_true")
    p.add_argument("--audit", default=None, help="append JSONL audit record to this path")
    a = p.parse_args(argv)
    v = evaluate_action(a.request, {"history": a.history}, audit_path=a.audit)
    print(json.dumps(v.to_dict(), indent=2) if a.json else render(a.request, v))
    return 0


if __name__ == "__main__":
    sys.exit(main())
