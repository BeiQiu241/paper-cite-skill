"""Structured task specs for Codex-managed pipeline steps."""

from typing import Any, Dict, List, Optional


def build_search_task(
    paper_analysis: Dict[str, Any],
    target_papers: int,
    crossref_email: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a structured Codex request for literature search."""
    return {
        "task_type": "literature_search",
        "instructions": [
            "Search for candidate academic references related to the target paper.",
            "Use available Codex search or browsing capabilities instead of external model APIs.",
            "Return JSON only.",
        ],
        "response_schema": {
            "type": "object",
            "required": ["candidates"],
        },
        "response_example": {
            "search_summary": "Short summary of search coverage.",
            "candidates": [
                {
                    "title": "Paper title",
                    "year": 2024,
                    "journal": "Journal or conference",
                    "abstract": "Short abstract",
                    "authors": ["Author A", "Author B"],
                    "doi": "10.xxxx/xxxx",
                    "url": "https://example.com/paper",
                    "source": "openalex",
                    "lang": "en",
                    "citations": 10,
                }
            ],
        },
        "input": {
            "paper_analysis": paper_analysis,
            "target_papers": target_papers,
            "crossref_email": crossref_email or "",
        },
    }


def validate_search_result(result: Any) -> List[Dict[str, Any]]:
    """Validate and normalize candidate papers."""
    if isinstance(result, dict):
        candidates = result.get("candidates", [])
    else:
        candidates = result

    if not isinstance(candidates, list):
        raise RuntimeError("[Codex-Search] Search result must be a list or an object with 'candidates'.")

    normalized: List[Dict[str, Any]] = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        title = (item.get("title") or "").strip()
        if not title:
            continue
        paper = dict(item)
        paper.setdefault("year", "")
        paper.setdefault("journal", "")
        paper.setdefault("abstract", "")
        paper.setdefault("authors", [])
        paper.setdefault("doi", "")
        paper.setdefault("url", "")
        paper.setdefault("source", "")
        paper.setdefault("lang", "")
        paper.setdefault("citations", 0)
        normalized.append(paper)

    if not normalized:
        raise RuntimeError("[Codex-Search] No valid candidate papers were returned.")

    return normalized
