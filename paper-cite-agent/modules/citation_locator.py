"""Citation placement task helpers."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Set


_UNSUITABLE_PATTERN = re.compile(
    r"^(figure\s*\d|fig\.?\s*\d|table\s*\d|"
    r"\u56fe\s*\d|\u8868\s*\d|"
    r"abstract|\u6458\u8981|keywords?|\u5173\u952e\u8bcd|"
    r"acknowledg(e)?ment|\u81f4\u8c22|"
    r"references|\u53c2\u8003\u6587\u732e|bibliography|works\s+cited|"
    r"contents?|table\s+of\s+contents|\u76ee\u5f55)",
    re.IGNORECASE,
)
_TOC_PATTERN = re.compile(r"^.{0,80}(?:\.{3,}|\u2026{2,})\s*\d+\s*$")
_BLANKISH_PATTERN = re.compile(r"^[\d\W_]+$")
_MIN_BODY_LENGTH = 40


def _candidate_paragraphs(
    paragraphs: List[Dict[str, Any]],
    max_paragraphs: int,
) -> List[Dict[str, Any]]:
    """Return paragraphs that are likely suitable for citation placement."""
    chosen: List[Dict[str, Any]] = []
    for para in paragraphs:
        if para.get("is_heading"):
            continue
        if _is_suitable_paragraph(para):
            chosen.append(para)
        if len(chosen) >= max_paragraphs:
            break
    return chosen


def build_citation_task(
    paragraphs: List[Dict[str, Any]],
    ranked_papers: List[Dict[str, Any]],
    max_paragraphs: int = 60,
) -> Dict[str, Any]:
    """Build a structured request for citation placement."""
    body_paragraphs = _candidate_paragraphs(paragraphs, max_paragraphs=max_paragraphs)
    return {
        "task_type": "citation_positioning",
        "instructions": [
            "Assign each selected reference to one suitable body paragraph.",
            "Never place citations in title, TOC, abstract, keywords, figure/table captions, acknowledgments, or references.",
            "Return JSON only.",
        ],
        "response_schema": {"type": "array"},
        "response_example": [
            {
                "paragraph_index": body_paragraphs[0]["index"] if body_paragraphs else 1,
                "cite_indices": [0],
                "reason": "This paragraph discusses the same method.",
            }
        ],
        "input": {
            "ranked_papers": [
                {
                    "index": idx,
                    "title": paper.get("title", ""),
                    "year": paper.get("year", ""),
                    "journal": paper.get("journal", ""),
                    "review_reason": paper.get("_review_reason", ""),
                }
                for idx, paper in enumerate(ranked_papers)
            ],
            "body_paragraphs": [
                {"index": para["index"], "text": para.get("text", "")[:500]}
                for para in body_paragraphs
            ],
        },
    }


def validate_citation_result(
    positions: Any,
    paragraphs: List[Dict[str, Any]],
    ranked_papers: List[Dict[str, Any]],
    max_paragraphs: int = 60,
    echo_logs: bool = False,
) -> List[Dict[str, Any]]:
    """Validate citation positions and fall back to a simple spread if needed."""
    body_paragraphs = _candidate_paragraphs(paragraphs, max_paragraphs=max_paragraphs)
    valid_indices: Set[int] = {para["index"] for para in body_paragraphs}
    paragraph_text = {para["index"]: para.get("text", "") for para in body_paragraphs}

    if isinstance(positions, dict):
        positions = positions.get("positions", [])
    if not isinstance(positions, list):
        raise RuntimeError("Citation positioning response must be a JSON array.")

    normalized: List[Dict[str, Any]] = []
    used_paragraphs: Set[int] = set()
    used_references: Set[int] = set()

    for item in positions:
        if not isinstance(item, dict):
            continue
        paragraph_index = item.get("paragraph_index")
        cite_indices = item.get("cite_indices", [])
        if not isinstance(paragraph_index, int) or paragraph_index not in valid_indices:
            continue
        if not isinstance(cite_indices, list):
            continue

        valid_refs = [
            ref_idx
            for ref_idx in cite_indices
            if isinstance(ref_idx, int) and 0 <= ref_idx < len(ranked_papers) and ref_idx not in used_references
        ]
        if not valid_refs or paragraph_index in used_paragraphs:
            continue

        used_paragraphs.add(paragraph_index)
        used_references.update(valid_refs)
        normalized.append(
            {
                "paragraph_index": paragraph_index,
                "cite_indices": valid_refs,
                "reason": str(item.get("reason", "") or "").strip(),
                "text": paragraph_text.get(paragraph_index, "")[:120],
                "cite_titles": [ranked_papers[idx].get("title", "") for idx in valid_refs],
            }
        )

    if not normalized and body_paragraphs and ranked_papers:
        normalized = _fallback_positions(body_paragraphs, ranked_papers)

    if echo_logs:
        print(f"  Selected {len(normalized)} citation positions")

    return normalized


def _fallback_positions(
    body_paragraphs: List[Dict[str, Any]],
    ranked_papers: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Spread references across the body when the model returns nothing usable."""
    limit = min(len(body_paragraphs), len(ranked_papers))
    if limit == 0:
        return []

    if limit == 1:
        chosen_indexes = [0]
    else:
        step = (len(body_paragraphs) - 1) / (limit - 1)
        chosen_indexes = [round(i * step) for i in range(limit)]

    fallback: List[Dict[str, Any]] = []
    for ref_idx, para_idx in enumerate(chosen_indexes):
        para = body_paragraphs[para_idx]
        fallback.append(
            {
                "paragraph_index": para["index"],
                "cite_indices": [ref_idx],
                "reason": "Fallback placement because no valid model result was returned.",
                "text": para.get("text", "")[:120],
                "cite_titles": [ranked_papers[ref_idx].get("title", "")],
            }
        )
    return fallback


def _is_suitable_paragraph(para: Dict[str, Any]) -> bool:
    """Return True when a paragraph can reasonably host a citation."""
    text = str(para.get("text", "") or "").strip()
    if len(text) < _MIN_BODY_LENGTH:
        return False
    if _UNSUITABLE_PATTERN.match(text):
        return False
    if _TOC_PATTERN.match(text):
        return False
    if _BLANKISH_PATTERN.match(text):
        return False
    return True
