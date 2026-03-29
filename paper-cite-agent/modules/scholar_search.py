"""
学术文献检索模块。

数据源（均为官方 API，无爬虫）：
  Crossref          → 英文期刊（按相关度，过滤 journal-article）
  Semantic Scholar  → 英文为主，支持中文查询，含引用数/摘要/PDF
  OpenAlex          → 英文/中文；institutions.country_code:cn 筛中国机构论文
  arXiv             → 预印本/最新论文（Atom XML API，无需 Key）
"""

import time
import re
import xml.etree.ElementTree as _ET
from typing import List, Dict, Any, Optional

from utils.api_client import get_with_retry, get_text_with_retry


# ─── Crossref ─────────────────────────────────────────────────────────────────

CROSSREF_BASE = "https://api.crossref.org/works"


def search_crossref(query: str, rows: int = 10,
                    email: Optional[str] = None) -> List[Dict[str, Any]]:
    headers = {"User-Agent": f"paper-cite-agent/1.0{f' (mailto:{email})' if email else ''}"}
    params = {
        "query": query,
        "rows": rows * 3,
        "select": ("DOI,title,author,published,abstract,is-referenced-by-count,"
                   "URL,container-title,volume,issue,page"),
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
            "journal": (item.get("container-title") or [""])[0],
            "volume": item.get("volume", ""),
            "issue": item.get("issue", ""),
            "pages": item.get("page", ""),
            "source": "crossref", "lang": "en",
        })
    return results


# ─── Semantic Scholar ──────────────────────────────────────────────────────────

SS_BASE = "https://api.semanticscholar.org/graph/v1/paper/search"


def search_semantic_scholar(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    params = {
        "query": query, "limit": limit,
        "fields": ("title,authors,year,externalIds,abstract,citationCount,"
                   "openAccessPdf,journal"),
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
        journal_obj = item.get("journal") or {}
        results.append({
            "title": title, "authors": authors, "year": year,
            "doi": doi, "url": url, "pdf_url": pdf_url,
            "abstract": item.get("abstract", "") or "",
            "citations": item.get("citationCount", 0) or 0,
            "journal": journal_obj.get("name", ""),
            "volume": journal_obj.get("volume", ""),
            "issue": "",
            "pages": journal_obj.get("pages", ""),
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


def _openalex_request(params: Dict, limit: int,
                      source_tag: str) -> List[Dict[str, Any]]:
    """OpenAlex 公共请求逻辑，提取带期刊元数据的结果。"""
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
        primary_loc = item.get("primary_location") or {}
        url = (f"https://doi.org/{doi}" if doi else
               primary_loc.get("landing_page_url", ""))
        abstract = _reconstruct_abstract(item.get("abstract_inverted_index"))
        lang = item.get("language", "en") or "en"

        # 期刊元数据
        source_info = primary_loc.get("source") or {}
        journal = source_info.get("display_name", "")
        biblio = item.get("biblio") or {}
        volume = biblio.get("volume", "") or ""
        issue = biblio.get("issue", "") or ""
        first_page = biblio.get("first_page", "") or ""
        last_page = biblio.get("last_page", "") or ""
        pages = f"{first_page}–{last_page}" if first_page and last_page else first_page

        results.append({
            "title": title, "authors": authors, "year": year,
            "doi": doi, "url": url, "abstract": abstract,
            "citations": item.get("cited_by_count", 0) or 0,
            "journal": journal, "volume": volume,
            "issue": issue, "pages": pages,
            "source": source_tag, "lang": lang,
        })
    return results


def search_openalex(query: str, limit: int = 10,
                    cn_only: bool = False) -> List[Dict[str, Any]]:
    """
    搜索 OpenAlex（英文为主）。
    cn_only=True → 仅返回中国机构发表的论文（主要是英文国际期刊）。
    """
    params = {
        "search": query,
        "per_page": min(limit * 2, 50),
        "select": ("id,title,authorships,publication_year,doi,"
                   "abstract_inverted_index,cited_by_count,language,"
                   "primary_location,biblio"),
        "sort": "relevance_score:desc",
    }
    if cn_only:
        params["filter"] = "institutions.country_code:cn"
    source_tag = "openalex_cn" if cn_only else "openalex"
    return _openalex_request(params, limit, source_tag)


def search_openalex_zh(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    搜索 OpenAlex 中的中文语言论文（language:zh）。
    返回真正的中文期刊论文，包含完整的期刊/卷期/页码信息。
    查询词须为英文（OpenAlex search 不支持中文字符）。
    """
    params = {
        "search": query,
        "per_page": min(limit * 2, 50),
        "filter": "language:zh",
        "select": ("id,title,authorships,publication_year,doi,"
                   "abstract_inverted_index,cited_by_count,language,"
                   "primary_location,biblio"),
        "sort": "relevance_score:desc",
    }
    return _openalex_request(params, limit, "openalex_zh")


# ─── arXiv ────────────────────────────────────────────────────────────────────

ARXIV_BASE = "http://export.arxiv.org/api/query"
_ARXIV_NS = {
    "atom":   "http://www.w3.org/2005/Atom",
    "arxiv":  "http://arxiv.org/schemas/atom",
}


def search_arxiv(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    使用 arXiv 官方 Atom API 搜索预印本/已发表论文（无需 API Key）。
    覆盖 CS、数学、物理、统计等学科，返回完整摘要与 PDF 链接。
    查询词须为英文。
    """
    params = {
        "search_query": f"all:{query}",
        "start": 0,
        "max_results": min(limit * 2, 50),
        "sortBy": "relevance",
        "sortOrder": "descending",
    }
    text = get_text_with_retry(ARXIV_BASE, params=params)
    if not text:
        return []

    try:
        root = _ET.fromstring(text)
    except _ET.ParseError as e:
        print(f"  [arXiv] XML 解析失败: {e}")
        return []

    results: List[Dict[str, Any]] = []
    for entry in root.findall("atom:entry", _ARXIV_NS):
        if len(results) >= limit:
            break

        title_el = entry.find("atom:title", _ARXIV_NS)
        title = (title_el.text or "").strip().replace("\n", " ") if title_el is not None else ""
        if not title:
            continue

        # 发布年份
        pub_el = entry.find("atom:published", _ARXIV_NS)
        year = 0
        if pub_el is not None and pub_el.text:
            try:
                year = int(pub_el.text[:4])
            except ValueError:
                pass

        # 作者列表
        authors = []
        for a in entry.findall("atom:author", _ARXIV_NS):
            name_el = a.find("atom:name", _ARXIV_NS)
            if name_el is not None and name_el.text:
                authors.append(name_el.text.strip())
        authors = authors[:6]

        # 摘要
        summary_el = entry.find("atom:summary", _ARXIV_NS)
        abstract = (summary_el.text or "").strip().replace("\n", " ") if summary_el is not None else ""

        # DOI（部分论文有）
        doi_el = entry.find("arxiv:doi", _ARXIV_NS)
        doi = (doi_el.text or "").strip() if doi_el is not None else ""

        # arXiv 页面 URL
        id_el = entry.find("atom:id", _ARXIV_NS)
        arxiv_url = (id_el.text or "").strip() if id_el is not None else ""

        # PDF URL
        pdf_url = ""
        for link in entry.findall("atom:link", _ARXIV_NS):
            if link.get("type") == "application/pdf":
                pdf_url = link.get("href", "")
                break

        # 期刊信息（已发表论文才有）
        journal_el = entry.find("arxiv:journal_ref", _ARXIV_NS)
        journal = (journal_el.text or "").strip() if journal_el is not None else ""

        url = f"https://doi.org/{doi}" if doi else arxiv_url

        results.append({
            "title": title,
            "authors": authors,
            "year": year,
            "doi": doi,
            "url": url,
            "pdf_url": pdf_url,
            "abstract": abstract,
            "citations": 0,
            "journal": journal,
            "volume": "",
            "issue": "",
            "pages": "",
            "source": "arxiv",
            "lang": "en",
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

    return mixed
