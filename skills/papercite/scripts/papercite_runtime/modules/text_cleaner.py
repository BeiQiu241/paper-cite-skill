"""Paragraph cleaning helpers."""

from __future__ import annotations

import re
from typing import Any, Dict, List


_TOC_PATTERN = re.compile(r"^.{0,80}(?:\.{3,}|…{2,})\s*\d+\s*$")
_HEADER_FOOTER_PATTERN = re.compile(
    r"(第\s*\d+\s*页|\bpage\b|copyright|confidential|draft)",
    re.IGNORECASE,
)
_REFERENCE_SECTION_PATTERN = re.compile(
    r"^(参考文献|references|bibliography|works cited)\s*$",
    re.IGNORECASE,
)


def clean_paragraphs(
    paragraphs: List[Dict[str, Any]],
    min_length: int = 20,
) -> List[Dict[str, Any]]:
    """Remove obvious noise before task generation."""
    cleaned: List[Dict[str, Any]] = []
    seen_texts: set[str] = set()
    in_references = False

    for para in paragraphs:
        text = str(para.get("text", "") or "").strip()
        if not text:
            continue

        if _REFERENCE_SECTION_PATTERN.match(text):
            in_references = True
        if in_references:
            continue

        if _TOC_PATTERN.match(text):
            continue
        if len(text) <= 80 and _HEADER_FOOTER_PATTERN.search(text):
            continue
        if not para.get("is_heading") and len(text) < min_length:
            continue
        if text in seen_texts:
            continue

        seen_texts.add(text)
        cleaned.append(dict(para))

    return cleaned


def merge_short_paragraphs(
    paragraphs: List[Dict[str, Any]],
    min_length: int = 60,
) -> List[Dict[str, Any]]:
    """Merge short adjacent body paragraphs to reduce fragmentation."""
    if not paragraphs:
        return []

    merged: List[Dict[str, Any]] = []
    buffer: Dict[str, Any] | None = None

    for para in paragraphs:
        if para.get("is_heading"):
            if buffer is not None:
                merged.append(buffer)
                buffer = None
            merged.append(dict(para))
            continue

        if buffer is None:
            buffer = dict(para)
            continue

        if len(str(buffer.get("text", ""))) < min_length:
            buffer["text"] = f"{buffer.get('text', '').strip()} {para.get('text', '').strip()}".strip()
        else:
            merged.append(buffer)
            buffer = dict(para)

    if buffer is not None:
        merged.append(buffer)

    return merged
