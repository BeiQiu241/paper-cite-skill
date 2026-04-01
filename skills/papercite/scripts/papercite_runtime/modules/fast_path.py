"""Generic single-response fast-track helpers for papercite."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from .citation_locator import _candidate_paragraphs, validate_citation_result
from .codex_task_specs import validate_search_result
from .paper_analyzer import validate_analysis_result


def build_fast_track_task(
    text_excerpt: str,
    paragraphs: List[Dict[str, Any]],
    cn_count: int,
    en_count: int,
    target_papers: int,
    max_paragraphs: int = 60,
) -> Dict[str, Any]:
    """Build one combined request for analysis, literature, and citation placement."""
    body_paragraphs = _candidate_paragraphs(paragraphs, max_paragraphs=max_paragraphs)
    return {
        "task_type": "fast_paper_citation_plan",
        "instructions": [
            "Analyze the paper, find real academic references, and assign citation positions in one response.",
            "Use available Codex browsing/search capabilities for literature selection.",
            f"Prefer about {cn_count} Chinese papers and {en_count} English papers when possible.",
            "Select references that support the topic, methods, dataset, or experiment setting.",
            "Only use the provided paragraph indices for citation placement.",
            "Prefer the compact standard response shape: `analysis`, `refs`, and `cites`.",
            "Inside `analysis`, prefer `problem`, `queries`, and `queries_zh` instead of longer key names.",
            "Inside `refs`, keep fields minimal: `title`, `authors`, `year`, `journal`, `doi`, `url`, `lang`, and `reason`.",
            "Inside `cites`, use `p` for paragraph index, `r` for one ref index or a list of ref indices, and `why` for the reason.",
            "Return JSON only.",
        ],
        "response_schema": {
            "type": "object",
            "required": ["analysis", "refs", "cites"],
        },
        "response_example": {
            "analysis": {
                "field": "Computer Vision",
                "field_zh": "计算机视觉",
                "keywords": ["object detection", "transformer"],
                "keywords_zh": ["目标检测", "Transformer"],
                "summary": "Two-sentence summary of the paper.",
                "problem": "Main research problem.",
                "methods": ["method 1", "method 2"],
                "queries": ["object detection transformer"],
                "queries_zh": ["目标检测 Transformer"],
            },
            "refs": [
                {
                    "title": "Paper title",
                    "year": 2024,
                    "journal": "Journal or conference",
                    "authors": ["Author A", "Author B"],
                    "doi": "10.xxxx/xxxx",
                    "url": "https://example.com/paper",
                    "lang": "en",
                    "reason": "Directly supports the method comparison.",
                }
            ],
            "cites": [
                {
                    "p": 12,
                    "r": 0,
                    "why": "This paragraph discusses the same method.",
                }
            ],
        },
        "input": {
            "text_excerpt": text_excerpt[:8000],
            "target_papers": target_papers,
            "cn_count": cn_count,
            "en_count": en_count,
            "body_paragraphs": [
                {"index": para["index"], "text": str(para.get("text", ""))[:500]}
                for para in body_paragraphs
            ],
        },
    }


def _first_present(payload: Dict[str, Any], *keys: str) -> Any:
    """Return the first present payload value among the provided keys."""
    for key in keys:
        if key in payload and payload.get(key) is not None:
            return payload.get(key)
    return None


def _normalize_analysis_payload(payload: Any) -> Any:
    """Accept both long and compact analysis payloads."""
    if not isinstance(payload, dict):
        return payload

    normalized = dict(payload)
    normalized["core_problem"] = _first_present(payload, "core_problem", "problem")
    normalized["search_queries"] = _first_present(payload, "search_queries", "queries")
    normalized["search_queries_zh"] = _first_present(payload, "search_queries_zh", "queries_zh")
    normalized["keywords_zh"] = _first_present(payload, "keywords_zh", "kw_zh")
    return normalized


def _normalize_reference_item(item: Any) -> Any:
    """Accept both long and compact reference items."""
    if not isinstance(item, dict):
        return item

    return {
        "title": _first_present(item, "title", "t") or "",
        "year": _first_present(item, "year", "y") or "",
        "journal": _first_present(item, "journal", "j") or "",
        "abstract": _first_present(item, "abstract", "abs") or "",
        "authors": _first_present(item, "authors", "a") or [],
        "doi": _first_present(item, "doi", "d") or "",
        "url": _first_present(item, "url", "u") or "",
        "source": _first_present(item, "source", "src") or "",
        "lang": _first_present(item, "lang", "l") or "",
        "citations": _first_present(item, "citations", "cites") or 0,
        "reason": _first_present(item, "reason", "why") or "",
    }


def _normalize_citation_item(item: Any) -> Any:
    """Accept both long and compact citation placement items."""
    if not isinstance(item, dict):
        return item

    cite_indices = _first_present(item, "cite_indices", "r", "refs")
    if isinstance(cite_indices, int):
        cite_indices = [cite_indices]

    return {
        "paragraph_index": _first_present(item, "paragraph_index", "p"),
        "cite_indices": cite_indices if isinstance(cite_indices, list) else [],
        "reason": _first_present(item, "reason", "why") or "",
    }


def validate_fast_track_result(
    result: Any,
    paragraphs: List[Dict[str, Any]],
    echo_logs: bool = False,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Validate the one-shot fast-track response payload."""
    if not isinstance(result, dict):
        raise RuntimeError("Fast-track response must be a JSON object.")

    analysis = validate_analysis_result(_normalize_analysis_payload(_first_present(result, "analysis", "a")))

    raw_references = _first_present(result, "refs", "selected_references", "references")
    if raw_references is None:
        raise RuntimeError("Fast-track response must contain `refs` (or a compatible legacy key).")
    if not isinstance(raw_references, list):
        raise RuntimeError("Fast-track response `refs` must be an array.")

    normalized_references = [_normalize_reference_item(item) for item in raw_references]
    ranked = validate_search_result({"candidates": normalized_references})
    for index, paper in enumerate(ranked):
        raw_item = normalized_references[index] if index < len(normalized_references) else {}
        paper["_review_reason"] = str(raw_item.get("reason", "") or "").strip()

    if echo_logs:
        cn_total = sum(1 for paper in ranked if str(paper.get("lang", "")).lower() == "zh")
        en_total = len(ranked) - cn_total
        print(f"  Selected {len(ranked)} papers (CN {cn_total} / EN {en_total})")

    raw_positions = _first_present(result, "cites", "citation_positions", "positions")
    normalized_positions = [_normalize_citation_item(item) for item in (raw_positions or [])]
    citation_positions = validate_citation_result(
        normalized_positions,
        paragraphs,
        ranked,
        echo_logs=echo_logs,
    )
    return analysis, ranked, citation_positions
