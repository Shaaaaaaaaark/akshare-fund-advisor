"""聊天消息辅助：构造 OpenAI 风格的 message dict。"""

from __future__ import annotations

from typing import Dict, List

Message = Dict[str, str]


def system(content: str) -> Message:
    return {"role": "system", "content": content}


def user(content: str) -> Message:
    return {"role": "user", "content": content}


def assistant(content: str) -> Message:
    return {"role": "assistant", "content": content}


def as_messages(*parts: Message) -> List[Message]:
    return list(parts)
