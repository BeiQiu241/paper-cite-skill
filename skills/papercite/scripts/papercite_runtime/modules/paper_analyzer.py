"""Paper analysis task helpers."""

from __future__ import annotations

from typing import Any, Dict, List


REQUIRED_FIELDS = ("field", "keywords", "search_queries")


def build_analysis_task(full_text: str) -> Dict[str, Any]:
    """Build a structured request for paper analysis."""
    return {
        "task_type": "paper_analysis",
        "instructions": [
            "Analyze the paper excerpt and return JSON only.",
            "Infer the research field, bilingual keywords, a short summary, methods, and search queries.",
            "Keep `search_queries` in English and `search_queries_zh` in Chinese academic wording.",
        ],
        "response_schema": {"type": "object", "required": list(REQUIRED_FIELDS)},
        "response_example": {
            "field": "Computer Vision",
            "field_zh": "计算机视觉",
            "keywords": ["object detection", "transformer", "remote sensing"],
            "keywords_zh": ["目标检测", "Transformer", "遥感图像"],
            "summary": "Two-sentence summary of the paper.",
            "core_problem": "Main research problem.",
            "methods": ["method 1", "method 2"],
            "search_queries": [
                "remote sensing object detection transformer",
                "oriented object detection aerial image",
            ],
            "search_queries_zh": [
                "遥感图像 目标检测 Transformer",
                "航拍图像 旋转目标检测",
            ],
        },
        "input": {"text_excerpt": full_text[:8000]},
    }


def _normalize_string_list(value: Any) -> List[str]:
    """Normalize a list of strings."""
    if value is None:
        return []
    if not isinstance(value, list):
        raise RuntimeError("Expected a list of strings in analysis response.")
    normalized: List[str] = []
    for item in value:
        if item is None:
            continue
        normalized.append(str(item).strip())
    return [item for item in normalized if item]


def validate_analysis_result(result: Any) -> Dict[str, Any]:
    """Validate and normalize the analysis payload."""
    if not isinstance(result, dict):
        raise RuntimeError("Paper analysis response must be a JSON object.")

    for field in REQUIRED_FIELDS:
        if field not in result:
            raise RuntimeError(f"Paper analysis response is missing required field `{field}`.")

    normalized = {
        "field": str(result.get("field", "") or "").strip(),
        "field_zh": str(result.get("field_zh", "") or "").strip(),
        "summary": str(result.get("summary", "") or "").strip(),
        "core_problem": str(result.get("core_problem", "") or "").strip(),
        "keywords": _normalize_string_list(result.get("keywords")),
        "keywords_zh": _normalize_string_list(result.get("keywords_zh")),
        "methods": _normalize_string_list(result.get("methods")),
        "search_queries": _normalize_string_list(result.get("search_queries")),
        "search_queries_zh": _normalize_string_list(result.get("search_queries_zh")),
    }

    if not normalized["field"]:
        raise RuntimeError("Paper analysis response must contain a non-empty `field`.")
    if not normalized["keywords"]:
        raise RuntimeError("Paper analysis response must contain at least one keyword.")
    if not normalized["search_queries"]:
        raise RuntimeError("Paper analysis response must contain at least one search query.")

    return normalized


def extract_abstract(paragraphs: List[Dict[str, Any]]) -> str:
    """Extract a likely abstract section from cleaned paragraphs."""
    abstract_lines: List[str] = []
    in_abstract = False

    for para in paragraphs:
        text = str(para.get("text", "") or "").strip()
        lowered = text.lower()

        if lowered in {"abstract", "摘要"}:
            in_abstract = True
            continue

        if not in_abstract:
            continue

        if para.get("is_heading") and para.get("level", 0) <= 2:
            break

        abstract_lines.append(text)
        if len(" ".join(abstract_lines)) >= 1800:
            break

    return "\n".join(abstract_lines).strip()
