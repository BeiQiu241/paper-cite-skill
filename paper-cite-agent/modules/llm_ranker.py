"""Reference selection task helpers."""

from __future__ import annotations

import re
from typing import Any, Dict, List


def _is_cn_paper(paper: Dict[str, Any]) -> bool:
    """Infer whether a paper is Chinese."""
    return str(paper.get("lang", "")).lower() == "zh" or bool(
        re.search(r"[\u4e00-\u9fff]", str(paper.get("title", "")))
    )


def build_review_task(
    candidates: List[Dict[str, Any]],
    paper_analysis: Dict[str, Any],
    cn_count: int,
    en_count: int,
) -> Dict[str, Any]:
    """Build a structured request for reference selection."""
    simplified_candidates = []
    for index, paper in enumerate(candidates):
        simplified_candidates.append(
            {
                "index": index,
                "title": paper.get("title", ""),
                "year": paper.get("year", ""),
                "journal": paper.get("journal", ""),
                "abstract": str(paper.get("abstract", "") or "")[:400],
                "authors": paper.get("authors", []),
                "lang_guess": "zh" if _is_cn_paper(paper) else "en",
            }
        )

    return {
        "task_type": "literature_review",
        "instructions": [
            "Select the most relevant references for the target paper.",
            "Return JSON only.",
            f"Prefer about {cn_count} Chinese papers and {en_count} English papers when possible.",
            "Choose papers that support the topic, method, dataset, or experiment setting.",
        ],
        "response_schema": {"type": "object", "required": ["selected"]},
        "response_example": {
            "selected": [
                {"index": 0, "reason": "Directly matches the paper topic."},
                {"index": 3, "reason": "Useful method baseline."},
            ]
        },
        "input": {
            "paper_analysis": paper_analysis,
            "cn_count": cn_count,
            "en_count": en_count,
            "candidates": simplified_candidates,
        },
    }


def validate_review_result(
    result: Any,
    candidates: List[Dict[str, Any]],
    echo_logs: bool = False,
) -> List[Dict[str, Any]]:
    """Validate and normalize selected papers."""
    if isinstance(result, dict):
        selected_items = result.get("selected", [])
    elif isinstance(result, list):
        selected_items = result
    else:
        raise RuntimeError("Literature review response must be a JSON object or array.")

    if not isinstance(selected_items, list) or not selected_items:
        raise RuntimeError("Literature review response must contain a non-empty `selected` array.")

    chosen: List[Dict[str, Any]] = []
    seen_indices: set[int] = set()

    for item in selected_items:
        if isinstance(item, int):
            index = item
            reason = ""
        elif isinstance(item, dict):
            index = item.get("index")
            reason = str(item.get("reason", "") or "").strip()
        else:
            continue

        if not isinstance(index, int) or not (0 <= index < len(candidates)) or index in seen_indices:
            continue

        paper = dict(candidates[index])
        paper["_review_reason"] = reason
        chosen.append(paper)
        seen_indices.add(index)

    if not chosen:
        raise RuntimeError("Literature review response did not contain any valid candidate index.")

    if echo_logs:
        cn_total = sum(1 for paper in chosen if _is_cn_paper(paper))
        en_total = len(chosen) - cn_total
        print(f"  Selected {len(chosen)} papers (CN {cn_total} / EN {en_total})")

    return chosen
