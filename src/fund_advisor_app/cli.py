"""Claude Code-style terminal interface backed by the shared Agent API."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence
from typing import Any

import httpx
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt

from .client import AgentApiClient

DEFAULT_API_URL = "http://127.0.0.1:8000"
TERMINAL_STATUSES = {
    "cannot_confirm",
    "stale_data",
    "failed",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fund-advisor",
        description="Interactive audited fund and stock research client",
    )
    parser.add_argument(
        "--api-url",
        default=os.environ.get("FUND_ADVISOR_API_URL", DEFAULT_API_URL),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("chat", help="start an interactive research session")
    ask = subparsers.add_parser("ask", help="ask one question through the API")
    ask.add_argument("question")
    ask.add_argument("--output", choices=("text", "json"), default="text")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    console = Console()
    try:
        with AgentApiClient(args.api_url) as client:
            if args.command == "chat":
                return _chat(client, console)
            return _ask(
                client,
                console,
                args.question,
                output=args.output,
            )
    except httpx.HTTPError as exc:
        console.print(
            f"[red]无法连接 Agent API：{type(exc).__name__}[/red]",
            highlight=False,
        )
        return 1


def _chat(client: AgentApiClient, console: Console) -> int:
    session_id = client.create_session().session_id
    console.print(
        Panel(
            "[bold]Fund Advisor[/bold]\n"
            "可信基金与股票研究助手\n\n"
            "[dim]输入 /help 查看命令；当前会话退出后不会保存。[/dim]",
            border_style="cyan",
        )
    )
    try:
        while True:
            try:
                message = Prompt.ask("\n[bold cyan]你[/bold cyan]").strip()
            except (EOFError, KeyboardInterrupt):
                console.print("\n[dim]会话已结束。[/dim]")
                return 0
            if not message:
                continue
            if message in {"/exit", "/quit"}:
                console.print("[dim]会话已结束。[/dim]")
                return 0
            if message == "/help":
                console.print(
                    "[dim]/new 新建会话  /clear 清屏  /exit 退出[/dim]"
                )
                continue
            if message == "/clear":
                console.clear()
                continue
            if message == "/new":
                client.delete_session(session_id)
                session_id = client.create_session().session_id
                console.print("[green]已开始新会话。[/green]")
                continue

            session_id, response = _consume(
                client,
                console,
                message,
                session_id=session_id,
                show_status=True,
            )
            if response is not None:
                _render_answer(console, response)
    finally:
        try:
            client.delete_session(session_id)
        except httpx.HTTPError:
            pass


def _ask(
    client: AgentApiClient,
    console: Console,
    question: str,
    *,
    output: str,
) -> int:
    _, response = _consume(
        client,
        console,
        question,
        session_id=None,
        show_status=output == "text",
    )
    if response is None:
        return 1
    if output == "json":
        console.print_json(json.dumps(response, ensure_ascii=False))
    else:
        _render_answer(console, response)
    return 1 if response.get("status") in TERMINAL_STATUSES else 0


def _consume(
    client: AgentApiClient,
    console: Console,
    message: str,
    *,
    session_id: str | None,
    show_status: bool,
) -> tuple[str | None, dict[str, Any] | None]:
    response_payload: dict[str, Any] | None = None
    last_status = ""
    for item in client.stream_message(message, session_id=session_id):
        if item.event == "session":
            session_id = str(item.data["session_id"])
        elif item.event == "status" and show_status:
            status = str(item.data.get("message") or "")
            tools = item.data.get("tools") or []
            if tools:
                status = f"{status}：{', '.join(str(tool) for tool in tools)}"
            if status and status != last_status:
                console.print(f"[dim]  · {status}[/dim]")
                last_status = status
        elif item.event == "result":
            response_payload = dict(item.data["response"])
        elif item.event == "error":
            console.print(
                f"[red]{item.data.get('message', '研究请求失败')}[/red]"
            )
    return session_id, response_payload


def _render_answer(console: Console, response: dict[str, Any]) -> None:
    answer = str(response.get("answer") or "当前没有可展示的回答。")
    console.print(
        Panel(
            Markdown(answer),
            title="研究助手",
            title_align="left",
            border_style="blue",
            padding=(1, 2),
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
