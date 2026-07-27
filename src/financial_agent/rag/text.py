"""Language-neutral text helpers used by retrieval channels."""

from __future__ import annotations

import re


def query_terms(text: str) -> set[str]:
    terms = {item.lower() for item in re.findall(r"[A-Za-z]{3,}", text)}
    for segment in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        maximum = min(4, len(segment))
        for size in range(2, maximum + 1):
            terms.update(segment[index : index + size] for index in range(len(segment) - size + 1))
    return terms
