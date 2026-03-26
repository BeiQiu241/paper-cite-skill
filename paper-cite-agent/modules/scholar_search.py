"""
学术文献检索模块。

可用免费数据源及策略：
  Crossref          → 英文期刊（按相关度，过滤 journal-article）
  Semantic Scholar  → 英文为主，少量中文
  OpenAlex          → 英文为主；用 institutions.country_code:cn 筛出中国机构论文

注意：知网/万方/维普均无免费公开 API，本模块会在结尾打印建议的知网搜索词。
"""

import time
import re
from typing import List, Dict, Any, Optional

from utils.api_client import get_with_retry


# ─── Crossref ─────────────────────────────────────────────────────────────────

CROSSREF_BASE = "https://api.crossref.org/works"


def search_crossref(query: str, rows: int = 10,
                    email: Optional[str] = None) -> List[Dict[str, Any]]:
    headers = {"User-Agent": f"paper-cite-agent/1.0{f' (mailto:{email})' if email else ''}"}
    params = {
        "query": query,
        "rows": rows * 3,
        "select": "DOI,title,author,published,abstract,is-referenced-by-count,URL",
        "sort": "relevance",
        "filter": "type:journal-article,from-pub-date:2000",
    }
    data = get_with_retry(CROSSREF_BASE, params=params, headers=headers)
    if not data:
        return []

    results = []
    for item in data.get("message", {}).get("items", []):
        if len(results) >= rows:
            break
        title = (item.get("title") or [""])[0]
        if not title or "[unknown]" in title.lower() or len(title) < 8:
            continue
        authors = []
        for a in (item.get("author") or [])[:5]:
            n = f"{a.get('given','')} {a.get('family','')}".strip()
            if n:
                authors.append(n)
        if not authors:
            continue
        year = ((item.get("published") or {}).get("date-parts") or [[]])[0]
        year = year[0] if year else 0
        if year and year < 2000:
            continue
        doi = item.get("DOI", "")
        results.append({
            "title": title, "authors": authors, "year": year,
            "doi": doi,
            "url": item.get("URL", f"https://doi.org/{doi}" if doi else ""),
            "abstract": item.get("abstract", ""),
            "citations": item.get("is-referenced-by-count", 0),
            "source": "crossref", "lang": "en",
        })
    return results


# ─── Semantic Scholar ──────────────────────────────────────────────────────────

SS_BASE = "https://api.semanticscholar.org/graph/v1/paper/search"


def search_semantic_scholar(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    params = {
        "query": query, "limit": limit,
        "fields": "title,authors,year,externalIds,abstract,citationCount,openAccessPdf",
    }
    data = get_with_retry(SS_BASE, params=params)
    if not data:
        return []

    results = []
    for item in data.get("data", []):
        title = item.get("title", "")
        if not title:
            continue
        authors = [a.get("name", "") for a in (item.get("authors") or [])[:5]]
        year = item.get("year", 0) or 0
        ext = item.get("externalIds") or {}
        doi = ext.get("DOI", "")
        arxiv = ext.get("ArXiv", "")
        url = (f"https://doi.org/{doi}" if doi else
               f"https://arxiv.org/abs/{arxiv}" if arxiv else "")
        pdf_url = (item.get("openAccessPdf") or {}).get("url", "")
        lang = "zh" if re.search(r'[\u4e00-\u9fff]', title) else "en"
        results.append({
            "title": title, "authors": authors, "year": year,
            "doi": doi, "url": url, "pdf_url": pdf_url,
            "abstract": item.get("abstract", "") or "",
            "citations": item.get("citationCount", 0) or 0,
            "source": "semantic_scholar", "lang": lang,
        })
    return results


# ─── OpenAlex ─────────────────────────────────────────────────────────────────

OPENALEX_BASE = "https://api.openalex.org/works"


def _reconstruct_abstract(inv: Optional[Dict]) -> str:
    if not inv:
        return ""
    try:
        pos_word = {}
        for word, positions in inv.items():
            for p in positions:
                pos_word[p] = word
        return " ".join(pos_word[i] for i in sorted(pos_word))
    except Exception:
        return ""


def search_openalex(query: str, limit: int = 10,
                    cn_only: bool = False) -> List[Dict[str, Any]]:
    """
    搜索 OpenAlex。
    cn_only=True 时追加 institutions.country_code:cn 过滤，
    返回中国机构发表的论文（通常为英文，但主题与中国研究紧密相关）。
    """
    params = {
        "search": query,
        "per_page": min(limit * 2, 50),
        "select": ("id,title,authorships,publication_year,doi,"
                   "abstract_inverted_index,cited_by_count,language,"
                   "open_access,primary_location"),
        "sort": "relevance_score:desc",
    }
    if cn_only:
        params["filter"] = "institutions.country_code:cn"

    data = get_with_retry(OPENALEX_BASE, params=params,
                          headers={"User-Agent": "paper-cite-agent/1.0"})
    if not data:
        return []

    results = []
    for item in data.get("results", []):
        if len(results) >= limit:
            break
        title = item.get("title", "")
        if not title or len(title) < 6:
            continue
        authors = []
        for auth in (item.get("authorships") or [])[:5]:
            name = (auth.get("author") or {}).get("display_name", "")
            if name:
                authors.append(name)
        year = item.get("publication_year", 0) or 0
        doi = (item.get("doi") or "").replace("https://doi.org/", "")
        url = f"https://doi.org/{doi}" if doi else (
            (item.get("primary_location") or {}).get("landing_page_url", ""))
        abstract = _reconstruct_abstract(item.get("abstract_inverted_index"))
        lang = item.get("language", "en") or "en"
        # 标记中国机构来源
        source_tag = "openalex_cn" if cn_only else "openalex"
        results.append({
            "title": title, "authors": authors, "year": year,
            "doi": doi, "url": url, "abstract": abstract,
            "citations": item.get("cited_by_count", 0) or 0,
            "source": source_tag, "lang": lang,
        })
    return results


# ─── 统一搜索入口 ───────────────────────────────────────────────────────────────

def search_literature(
    queries: List[str],
    queries_zh: Optional[List[str]] = None,
    max_per_query: int = 8,
    use_semantic_scholar: bool = True,
    crossref_email: Optional[str] = None,
    zh_ratio: float = 0.55,
) -> List[Dict[str, Any]]:
    """
    多源搜索，中英文混合结果。

    "中文文献"策略（因知网等无免费 API）：
      1. OpenAlex + institutions.country_code:cn  → 中国机构发表的英/中文论文
      2. Semantic Scholar + 中文关键词            → 少量中文标题论文
      3. 程序结束时打印知网建议搜索词，供用户手动查询
    """
    en_pool: List[Dict] = []
    cn_pool: List[Dict] = []   # 中国机构来源或中文标题
    seen: set = set()

    def _add(r: Dict, pool: List):
        key = r["title"].lower()[:60]
        if key not in seen:
            seen.add(key)
            pool.append(r)

    # ── 英文查询 ──────────────────────────────────────────────
    for q in queries:
        if not q.strip():
            continue
        print(f"  [Search-EN] {q!r}")

        # Crossref（英文期刊）
        for r in search_crossref(q, rows=max_per_query, email=crossref_email):
            _add(r, en_pool)
        time.sleep(0.3)

        # Semantic Scholar
        if use_semantic_scholar:
            for r in search_semantic_scholar(q, limit=max_per_query):
                _add(r, cn_pool if r["lang"] == "zh" else en_pool)
            time.sleep(0.3)

        # OpenAlex 英文
        for r in search_openalex(q, limit=max_per_query, cn_only=False):
            _add(r, en_pool)
        time.sleep(0.3)

    # ── 中文/中国研究查询 ────────────────────────────────────
    # 策略：把中文关键词翻译成英文后用 cn_only 过滤；
    # 同时用原始中文词搜 Semantic Scholar
    cn_queries = queries_zh or []
    # 也用英文查询词+CN过滤搜一遍（弥补中文词搜不到的问题）
    cn_en_queries = queries[:2]  # 取前两条英文词

    for q in cn_en_queries:
        if not q.strip():
            continue
        print(f"  [Search-CN机构] {q!r}")
        for r in search_openalex(q, limit=max_per_query, cn_only=True):
            _add(r, cn_pool)
        time.sleep(0.3)

    for q in cn_queries:
        if not q.strip():
            continue
        print(f"  [Search-ZH] {q!r}")
        if use_semantic_scholar:
            for r in search_semantic_scholar(q, limit=max_per_query):
                _add(r, cn_pool if r["lang"] == "zh" else en_pool)
            time.sleep(0.3)

    print(f"  [Search] 英文来源: {len(en_pool)} 篇，中国机构/中文来源: {len(cn_pool)} 篇")

    # ── 按比例混合 ────────────────────────────────────────────
    total = len(en_pool) + len(cn_pool)
    if total == 0:
        return []

    zh_target = round(total * zh_ratio)
    en_target = total - zh_target

    mixed = cn_pool[:zh_target] + en_pool[:en_target]
    # 不足时互补
    if len(cn_pool) < zh_target:
        mixed += en_pool[en_target: en_target + (zh_target - len(cn_pool))]
    if len(en_pool) < en_target:
        mixed += cn_pool[zh_target: zh_target + (en_target - len(en_pool))]

    cn_count = sum(1 for r in mixed if r.get("source", "").endswith("_cn")
                   or r.get("lang") == "zh")
    print(f"  [Search] 合并 {len(mixed)} 篇（中国机构/中文 {cn_count} 篇 / 其他 {len(mixed)-cn_count} 篇）")

    # ── 打印知网建议搜索词 ────────────────────────────────────
    if cn_queries:
        print("\n  ┌─ 知网/万方手动搜索建议（免费 API 不可用）─────────────")
        for q in cn_queries:
            print(f"  │  {q}")
        print("  │  → https://www.cnki.net/  |  https://www.wanfangdata.com.cn/")
        print("  └───────────────────────────────────────────────────────\n")

    return mixed
