"""CLI entry point for the single-turn LangGraph agent."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Sequence

from .graph import run_agent
from .state import AgentStatus


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audited LangGraph research agent for Chinese funds and stocks",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    ask = subparsers.add_parser("ask", help="run one research question")
    ask.add_argument("--question", required=True, help="research question")
    ask.add_argument(
        "--output",
        choices=("text", "json"),
        default="text",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        response = asyncio.run(run_agent(args.question))
    except Exception as exc:
        payload = {
            "status": AgentStatus.FAILED.value,
            "error": {
                "code": "AGENT_RUNTIME_ERROR",
                "message": "LangGraph Agent 执行失败",
                "details": {"reason": type(exc).__name__},
            },
        }
        print(json.dumps(payload, ensure_ascii=False))
        return 1

    if args.output == "json":
        print(
            json.dumps(
                response.model_dump(mode="json"),
                ensure_ascii=False,
            )
        )
    else:
        print(response.answer)

    if response.status in {
        AgentStatus.CANNOT_CONFIRM,
        AgentStatus.STALE_DATA,
        AgentStatus.FAILED,
    }:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
