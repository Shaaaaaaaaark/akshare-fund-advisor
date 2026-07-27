"""Structure-aware chunking that preserves section paths and page ranges."""

from __future__ import annotations

from .models import ParsedBlock


def chunk_blocks(
    blocks: list[ParsedBlock],
    *,
    maximum_chars: int = 1800,
    overlap_chars: int = 180,
) -> list[ParsedBlock]:
    chunks: list[ParsedBlock] = []
    current_text = ""
    current_section: list[str] = []
    page_start: int | None = None

    def flush() -> None:
        nonlocal current_text, current_section, page_start
        if not current_text.strip():
            return
        chunks.append(
            ParsedBlock(
                text=current_text.strip(),
                page=page_start,
                section_path=current_section,
                block_type="chunk",
            )
        )
        current_text = ""
        current_section = []
        page_start = None

    for block in blocks:
        text = block.text.strip()
        if not text:
            continue
        if current_text and (
            len(current_text) + len(text) + 2 > maximum_chars
            or block.section_path != current_section
        ):
            flush()
        if not current_text:
            current_section = list(block.section_path)
            page_start = block.page
        if len(text) > maximum_chars and block.block_type != "table":
            step = max(maximum_chars - overlap_chars, 1)
            for offset in range(0, len(text), step):
                piece = text[offset : offset + maximum_chars]
                if current_text:
                    flush()
                current_text = piece
                current_section = list(block.section_path)
                page_start = block.page
                flush()
            continue
        current_text = f"{current_text}\n\n{text}".strip()
    flush()

    if overlap_chars <= 0:
        return chunks
    overlapped: list[ParsedBlock] = []
    previous: ParsedBlock | None = None
    for chunk in chunks:
        text = chunk.text
        if previous is not None and previous.section_path == chunk.section_path:
            prefix = previous.text[-overlap_chars:].strip()
            if prefix and not text.startswith(prefix):
                text = f"{prefix}\n\n{text}"
        overlapped.append(chunk.model_copy(update={"text": text}))
        previous = chunk
    return overlapped
