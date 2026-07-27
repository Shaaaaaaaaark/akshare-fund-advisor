"""Deterministic tool-routing evaluation.

This runner intentionally does not call AKShare or an LLM. It measures the
stable routing layer separately from upstream availability.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from financial_agent.orchestration.intent import classify_by_rules
from financial_agent.orchestration.planner import build_tool_plan


def evaluate(path: Path) -> dict[str, object]:
    cases = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    results: list[dict[str, object]] = []
    passed = 0
    for case in cases:
        decision = classify_by_rules(case["query"])
        plan = build_tool_plan(decision.intent, decision.entities)
        actual_tools = [item.tool for item in plan]
        ok = (
            decision.intent.value == case["expected_intent"]
            and actual_tools == case["expected_tools"]
        )
        passed += int(ok)
        results.append(
            {
                "case_id": case["case_id"],
                "passed": ok,
                "actual_intent": decision.intent.value,
                "actual_tools": actual_tools,
            }
        )
    total = len(cases)
    return {
        "total": total,
        "passed": passed,
        "accuracy": passed / total if total else 0,
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "dataset",
        nargs="?",
        type=Path,
        default=Path("evals/datasets/tool_routing.jsonl"),
    )
    args = parser.parse_args()
    report = evaluate(args.dataset)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["accuracy"] < 0.98:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
