"""文献评分与筛选模块：对候选文献按相关度排序。"""

import math
from typing import List, Dict, Any, Optional

from utils.embeddings import EmbeddingModel


def _is_cn(paper: Dict[str, Any]) -> bool:
    """判断是否为中国机构/中文文献。"""
    return (
        paper.get("source", "").endswith("_cn")
        or paper.get("lang") == "zh"
    )


def score_literature(
    papers: List[Dict[str, Any]],
    paper_analysis: Dict[str, Any],
    top_k: int = 5,
    cn_count: Optional[int] = None,
    en_count: Optional[int] = None,
    similarity_threshold: float = 0.1,
    embedding_model: EmbeddingModel = None,
) -> List[Dict[str, Any]]:
    """
    对候选文献评分，分中英文独立排序后合并返回。

    优先级：
      若指定 cn_count / en_count，则分别取各语种 top-N；
      否则退化为按总分取 top_k（不区分语种）。

    评分因素：
    - 语义相似度（与论文摘要 + 关键词）
    - 引用数（对数归一化）
    - 年份（近 20 年线性加权）
    """
    if not papers:
        return []

    if embedding_model is None:
        embedding_model = EmbeddingModel()

    # 构建查询文本（中英双语合并）
    query_parts = []
    for field in ("summary", "core_problem", "field_zh"):
        v = paper_analysis.get(field)
        if v:
            query_parts.append(v)
    for field in ("keywords", "keywords_zh"):
        v = paper_analysis.get(field)
        if v:
            query_parts.append(" ".join(v))
    query_text = " ".join(query_parts)

    max_citations = max((p.get("citations", 0) or 0 for p in papers), default=1) or 1
    current_year = 2025

    scored = []
    for paper in papers:
        paper_text = (paper.get("title") or "") + " " + (paper.get("abstract") or "")
        sim_score = embedding_model.similarity(query_text, paper_text)

        cit = paper.get("citations", 0) or 0
        cit_score = math.log1p(cit) / math.log1p(max_citations)

        year = paper.get("year", 0) or 0
        age = current_year - year if year > 0 else 20
        year_score = max(0.0, 1.0 - age / 20.0)

        total = 0.60 * sim_score + 0.25 * cit_score + 0.15 * year_score

        if sim_score >= similarity_threshold:
            scored.append({**paper, "_score": round(total, 4)})

    scored.sort(key=lambda x: x["_score"], reverse=True)

    # ── 按中英文分池取数 ──────────────────────────────────────────
    if cn_count is not None or en_count is not None:
        cn_want = cn_count if cn_count is not None else top_k
        en_want = en_count if en_count is not None else top_k

        cn_pool = [p for p in scored if _is_cn(p)]
        en_pool = [p for p in scored if not _is_cn(p)]

        result = cn_pool[:cn_want] + en_pool[:en_want]
        # 按分数重新排序（让输出顺序一致）
        result.sort(key=lambda x: x["_score"], reverse=True)
        return result

    return scored[:top_k]
