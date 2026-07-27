"""MinerU adapter with a lightweight PDF/text fallback."""

from __future__ import annotations

import asyncio
import re
import shlex
import tempfile
from pathlib import Path
from typing import Protocol

from pypdf import PdfReader

from .models import ParsedBlock


class DocumentParser(Protocol):
    async def parse(self, path: Path) -> list[ParsedBlock]: ...


class MinerUParser:
    """Run a configured MinerU CLI without invoking a shell."""

    def __init__(self, command: str) -> None:
        if not command.strip():
            raise ValueError("MinerU command 不能为空")
        self._command = command

    async def parse(self, path: Path) -> list[ParsedBlock]:
        with tempfile.TemporaryDirectory(prefix="finagent-mineru-") as temporary:
            output = Path(temporary)
            parts = [
                item.format(input=str(path), output=str(output))
                for item in shlex.split(self._command)
            ]
            if not any("{input}" in item for item in shlex.split(self._command)):
                parts.extend(["-p", str(path)])
            if not any("{output}" in item for item in shlex.split(self._command)):
                parts.extend(["-o", str(output)])
            process = await asyncio.create_subprocess_exec(
                *parts,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await process.communicate()
            if process.returncode != 0:
                raise RuntimeError(
                    f"MinerU 解析失败：{stderr.decode('utf-8', errors='replace')[:500]}"
                )
            markdown_files = sorted(output.rglob("*.md"))
            if not markdown_files:
                raise RuntimeError("MinerU 没有生成 Markdown 结果")
            text = "\n\n".join(
                item.read_text(encoding="utf-8", errors="replace") for item in markdown_files
            )
            return parse_markdown_blocks(text)


class LightweightParser:
    async def parse(self, path: Path) -> list[ParsedBlock]:
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            return await asyncio.to_thread(self._parse_pdf, path)
        if suffix in {".md", ".markdown", ".txt"}:
            text = await asyncio.to_thread(
                path.read_text,
                encoding="utf-8",
                errors="replace",
            )
            return parse_markdown_blocks(text)
        raise ValueError(f"不支持的文档格式：{suffix}")

    @staticmethod
    def _parse_pdf(path: Path) -> list[ParsedBlock]:
        reader = PdfReader(str(path))
        blocks: list[ParsedBlock] = []
        for page_number, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            for paragraph in _paragraphs(text):
                blocks.append(ParsedBlock(text=paragraph, page=page_number))
        return blocks


def parse_markdown_blocks(text: str) -> list[ParsedBlock]:
    section_stack: list[str] = []
    blocks: list[ParsedBlock] = []
    current: list[str] = []

    def flush() -> None:
        if current:
            paragraph = "\n".join(current).strip()
            if paragraph:
                blocks.append(
                    ParsedBlock(
                        text=paragraph,
                        section_path=list(section_stack),
                        block_type=(
                            "table" if "|" in paragraph and "\n" in paragraph else "paragraph"
                        ),
                    )
                )
            current.clear()

    for line in text.splitlines():
        heading = re.match(r"^(#{1,6})\s+(.+)$", line.strip())
        if heading:
            flush()
            level = len(heading.group(1))
            section_stack[:] = section_stack[: level - 1]
            section_stack.append(heading.group(2).strip())
            continue
        if not line.strip():
            flush()
        else:
            current.append(line.rstrip())
    flush()
    return blocks


def _paragraphs(text: str) -> list[str]:
    return [
        item.strip()
        for item in re.split(r"\n{2,}|(?<=[。！？])\s*", text)
        if len(item.strip()) >= 10
    ]
