"""LLM 驱动的文献搜索：让模型自主决定搜索策略和查询词。

支持两种后端：
  - Anthropic SDK（默认，tool_use 格式）
  - OpenAI SDK（openai_compat=True，function calling 格式，适用于 linkapi 等 OAI 兼容接口）
"""

import json
import time
from typing import List, Dict, Any, Optional

from modules.scholar_search import (
    search_crossref,
    search_semantic_scholar,
    search_openalex,
    search_openalex_zh,
    search_arxiv,
)


# ─── 工具定义（Anthropic 格式，OpenAI 格式由转换函数生成）─────────────────────

_TOOLS_ANTHROPIC = [
    {
        "name": "search_crossref",
        "description": (
            "搜索 Crossref 英文期刊数据库（journal-article，2000年以后）。"
            "适合搜索高质量英文学术期刊论文。查询词须为英文。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "英文搜索关键词"},
                "rows": {
                    "type": "integer",
                    "description": "返回结果数量，默认 10，最大 20",
                    "default": 10,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_semantic_scholar",
        "description": (
            "搜索 Semantic Scholar 数据库，支持中英文查询，包含引用数和摘要。"
            "中文关键词可直接使用，能返回少量中文标题论文。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "中文或英文搜索关键词"},
                "limit": {
                    "type": "integer",
                    "description": "返回结果数量，默认 10，最大 20",
                    "default": 10,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_openalex",
        "description": (
            "搜索 OpenAlex 数据库（英文论文为主）。"
            "设 cn_only=true 时仅返回中国机构（country_code:cn）发表的论文（多为英文国际期刊）。"
            "查询词须为英文。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "英文搜索关键词"},
                "limit": {
                    "type": "integer",
                    "description": "返回结果数量，默认 10，最大 20",
                    "default": 10,
                },
                "cn_only": {
                    "type": "boolean",
                    "description": "true = 只返回中国机构发表的论文",
                    "default": False,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_openalex_zh",
        "description": (
            "【中文论文首选，最可靠】搜索 OpenAlex 中文语言论文（language:zh 过滤）。"
            "返回发表在《计算机科学》《软件学报》《中文信息学报》等中文期刊上的论文，"
            "含完整期刊名、卷期、页码，无需爬虫、稳定可用。"
            "查询词须为英文，建议多次调用不同查询词以获取更多中文论文。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "英文搜索关键词"},
                "limit": {
                    "type": "integer",
                    "description": "返回结果数量，默认 10，最大 20",
                    "default": 10,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_arxiv",
        "description": (
            "搜索 arXiv 预印本数据库（官方 Atom API，无需 API Key，稳定可靠）。"
            "覆盖计算机科学、数学、物理、统计等学科的最新论文，含完整摘要和 PDF 链接。"
            "适合搜索前沿技术论文和尚未发表在期刊上的预印本。查询词须为英文。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "英文搜索关键词"},
                "limit": {
                    "type": "integer",
                    "description": "返回结果数量，默认 10，最大 30",
                    "default": 10,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "finish_search",
        "description": (
            "完成文献搜索。当你认为已收集到足够且多样化的候选文献时调用此工具。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "简要说明搜索策略和结果",
                },
            },
            "required": ["summary"],
        },
    },
]


def _to_openai_tools(anthropic_tools: List[Dict]) -> List[Dict]:
    """将 Anthropic tool 定义转换为 OpenAI function calling 格式。"""
    result = []
    for t in anthropic_tools:
        result.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
            },
        })
    return result


# ─── 工具执行（两种格式共用）──────────────────────────────────────────────────

def _execute_tool(tool_name: str, tool_input: Dict, crossref_email: str) -> List[Dict]:
    """执行搜索工具并返回结果列表。"""
    if tool_name == "search_crossref":
        return search_crossref(
            tool_input["query"],
            rows=min(int(tool_input.get("rows", 10)), 20),
            email=crossref_email,
        )
    elif tool_name == "search_semantic_scholar":
        return search_semantic_scholar(
            tool_input["query"],
            limit=min(int(tool_input.get("limit", 10)), 20),
        )
    elif tool_name == "search_openalex":
        return search_openalex(
            tool_input["query"],
            limit=min(int(tool_input.get("limit", 10)), 20),
            cn_only=bool(tool_input.get("cn_only", False)),
        )
    elif tool_name == "search_openalex_zh":
        return search_openalex_zh(
            tool_input["query"],
            limit=min(int(tool_input.get("limit", 10)), 20),
        )
    elif tool_name == "search_arxiv":
        return search_arxiv(
            tool_input["query"],
            limit=min(int(tool_input.get("limit", 10)), 30),
        )
    return []


# ─── 主函数 ────────────────────────────────────────────────────────────────────

def llm_search_literature(
    paper_analysis: Dict[str, Any],
    model: str = "claude-opus-4-6",
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    timeout_ms: Optional[int] = None,
    max_iterations: int = 12,
    target_papers: int = 30,
    crossref_email: Optional[str] = None,
    openai_compat: bool = False,
) -> List[Dict[str, Any]]:
    """
    让 LLM 自主规划搜索策略，通过工具调用各学术数据库，
    返回去重后的候选文献列表。

    参数：
        openai_compat : True = 使用 OpenAI SDK（适用于 linkapi 等 OAI 兼容接口）
                        False = 使用 Anthropic SDK（默认）
    """
    # ── 构建提示词 ────────────────────────────────────────────────
    field = paper_analysis.get("field", "")
    field_zh = paper_analysis.get("field_zh", "")
    keywords = paper_analysis.get("keywords", [])
    keywords_zh = paper_analysis.get("keywords_zh", [])
    summary = (paper_analysis.get("summary") or "")[:400]
    core_problem = paper_analysis.get("core_problem", "")
    methods = paper_analysis.get("methods", [])
    queries_hint = paper_analysis.get("search_queries", [])
    queries_zh_hint = paper_analysis.get("search_queries_zh", [])

    system_prompt = f"""你是专业的学术文献检索助手。请为以下论文搜索相关参考文献。

## 论文信息
- 研究领域：{field}（{field_zh}）
- 英文关键词：{', '.join(keywords)}
- 中文关键词：{', '.join(keywords_zh)}
- 核心问题：{core_problem}
- 研究方法：{', '.join(methods)}
- 摘要：{summary}

## 可用工具（均为官方 API，无爬虫）
| 工具 | 数据源 | 特点 |
|------|--------|------|
| `search_semantic_scholar` | Semantic Scholar | 引用数、摘要、开放获取 PDF，支持中英文查询 |
| `search_arxiv` | arXiv | 预印本/最新论文，CS/数学/物理，英文查询 |
| `search_crossref` | Crossref | 英文期刊，高质量元数据，英文查询 |
| `search_openalex` | OpenAlex | 英文为主；cn_only=true 筛中国机构论文 |
| `search_openalex_zh` | OpenAlex | 中文语言论文，英文查询词 |

## 搜索策略
1. **目标**：收集约 {target_papers} 篇候选文献
2. **英文/前沿论文**：
   - `search_arxiv`（3-4 组不同查询词，limit=15）→ 最新预印本和顶会论文
   - `search_semantic_scholar`（2-3 组查询词）→ 带引用数的主流英文期刊
   - `search_crossref` 或 `search_openalex` 补充
3. **中文论文（目标占55%）**：
   - `search_openalex_zh`（3-4 组英文查询词，limit=15）→ 中文期刊论文，最可靠
   - `search_openalex`（cn_only=true）→ 中国机构发表的英文国际期刊
4. **覆盖度**：对每个主要主题/关键词至少搜索一次，使用多样化查询词
5. **效率**：若某工具连续返回0结果则停止调用，收集足够文献后调用 finish_search

## 参考查询词
- 英文：{queries_hint}
- 中文（用于 openalex_zh 英文查询）：根据中文关键词 {', '.join(keywords_zh[:4])} 翻译组合
"""

    # ── 收集结果 ──────────────────────────────────────────────────
    all_papers: List[Dict] = []
    seen: set = set()

    def _add(papers: List[Dict]) -> int:
        added = 0
        for p in papers:
            key = (p.get("title") or "").lower()[:60]
            if key and key not in seen:
                seen.add(key)
                all_papers.append(p)
                added += 1
        return added

    def _log_progress(result_papers: List[Dict], new_count: int) -> None:
        _CN_SOURCES = {"openalex_cn", "openalex_zh"}
        cn_total = sum(
            1 for p in all_papers
            if p.get("source", "") in _CN_SOURCES or p.get("lang") == "zh"
        )
        print(f"  [LLM-Search]   → 新增 {new_count} 篇 | 累计 {len(all_papers)} 篇（中国机构/中文 {cn_total}）")

    def _make_feedback(result_papers: List[Dict], new_count: int, error_msg: str = "") -> str:
        sample = [
            {
                "title": p["title"][:70],
                "year": p.get("year"),
                "citations": p.get("citations", 0),
                "lang": p.get("lang", "en"),
            }
            for p in result_papers[:4]
        ]
        fb: Dict[str, Any] = {
            "found": len(result_papers),
            "new_added": new_count,
            "total_collected": len(all_papers),
            "sample_titles": sample,
        }
        if error_msg:
            fb["error"] = error_msg
        return json.dumps(fb, ensure_ascii=False)

    if openai_compat:
        _run_openai_loop(
            model=model, api_key=api_key, base_url=base_url, timeout_ms=timeout_ms,
            system_prompt=system_prompt, max_iterations=max_iterations,
            crossref_email=crossref_email or "",
            _add=_add, _log_progress=_log_progress, _make_feedback=_make_feedback,
            all_papers=all_papers,
        )
    else:
        _run_anthropic_loop(
            model=model, api_key=api_key, base_url=base_url, timeout_ms=timeout_ms,
            system_prompt=system_prompt, max_iterations=max_iterations,
            crossref_email=crossref_email or "",
            _add=_add, _log_progress=_log_progress, _make_feedback=_make_feedback,
        )

    _CN_SOURCES = {"openalex_cn", "openalex_zh"}
    cn_count = sum(
        1 for p in all_papers
        if p.get("source", "") in _CN_SOURCES or p.get("lang") == "zh"
    )
    print(
        f"  [LLM-Search] 合计 {len(all_papers)} 篇"
        f"（中国机构/中文 {cn_count} 篇 / 其他 {len(all_papers)-cn_count} 篇）"
    )
    return all_papers


# ─── Anthropic 工具调用循环 ────────────────────────────────────────────────────

def _run_anthropic_loop(
    model, api_key, base_url, timeout_ms,
    system_prompt, max_iterations, crossref_email,
    _add, _log_progress, _make_feedback,
):
    import anthropic
    import httpx

    client_kwargs: Dict[str, Any] = {}
    if api_key:
        client_kwargs["api_key"] = api_key
    if base_url:
        client_kwargs["base_url"] = base_url
    if timeout_ms:
        client_kwargs["timeout"] = httpx.Timeout(timeout_ms / 1000.0)
    client = anthropic.Anthropic(**client_kwargs)

    messages = [{"role": "user", "content": "请开始搜索与该论文相关的参考文献。"}]

    for _ in range(max_iterations):
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            system=system_prompt,
            tools=_TOOLS_ANTHROPIC,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        done = False

        for block in response.content:
            if not hasattr(block, "type") or block.type != "tool_use":
                continue

            tool_name = block.name
            tool_input = block.input or {}
            print(f"  [LLM-Search] {tool_name}({json.dumps(tool_input, ensure_ascii=False, separators=(',',':'))})")

            if tool_name == "finish_search":
                print(f"  [LLM-Search] 完成: {tool_input.get('summary', '')}")
                done = True
                tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": "搜索完成。"})
                break

            result_papers: List[Dict] = []
            error_msg = ""
            try:
                result_papers = _execute_tool(tool_name, tool_input, crossref_email)
                time.sleep(0.3)
            except Exception as exc:
                error_msg = str(exc)
                print(f"  [LLM-Search]   ✗ {exc}")

            new_count = _add(result_papers)
            _log_progress(result_papers, new_count)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": _make_feedback(result_papers, new_count, error_msg),
            })

        if done:
            break
        if response.stop_reason == "end_turn" and not tool_results:
            break
        if tool_results:
            messages.append({"role": "user", "content": tool_results})


# ─── OpenAI function calling 循环（直接 HTTP，不依赖 SDK 版本）──────────────

def _run_openai_loop(
    model, api_key, base_url, timeout_ms,
    system_prompt, max_iterations, crossref_email,
    _add, _log_progress, _make_feedback,
    all_papers,
):
    import requests as _req

    # 确保 base_url 末尾无斜杠
    endpoint_base = (base_url or "https://api.openai.com").rstrip("/")
    url = f"{endpoint_base}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key or ''}",
        "Content-Type": "application/json",
    }
    timeout_s = (timeout_ms / 1000.0) if timeout_ms else 120.0

    oai_tools = _to_openai_tools(_TOOLS_ANTHROPIC)
    messages: List[Dict] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "请开始搜索与该论文相关的参考文献。"},
    ]

    for _ in range(max_iterations):
        payload = {
            "model": model,
            "max_tokens": 4096,
            "messages": messages,
            "tools": oai_tools,
            "tool_choice": "auto",
        }
        resp = _req.post(url, headers=headers, json=payload, timeout=timeout_s)
        resp.raise_for_status()
        data: Dict = resp.json()

        choice = data["choices"][0]
        msg = choice["message"]
        finish_reason = choice.get("finish_reason", "")

        # 将助手消息加入历史
        messages.append(msg)

        tool_calls = msg.get("tool_calls") or []
        if not tool_calls or finish_reason == "stop":
            break  # 模型主动结束

        done = False
        for tc in tool_calls:
            tool_name = tc["function"]["name"]
            try:
                tool_input = json.loads(tc["function"]["arguments"])
            except json.JSONDecodeError:
                tool_input = {}
            tc_id = tc["id"]

            print(f"  [LLM-Search] {tool_name}({json.dumps(tool_input, ensure_ascii=False, separators=(',',':'))})")

            if tool_name == "finish_search":
                print(f"  [LLM-Search] 完成: {tool_input.get('summary', '')}")
                done = True
                messages.append({"role": "tool", "tool_call_id": tc_id, "content": "搜索完成。"})
                break

            result_papers: List[Dict] = []
            error_msg = ""
            try:
                result_papers = _execute_tool(tool_name, tool_input, crossref_email)
                time.sleep(0.3)
            except Exception as exc:
                error_msg = str(exc)
                print(f"  [LLM-Search]   ✗ {exc}")

            new_count = _add(result_papers)
            _log_progress(result_papers, new_count)
            messages.append({
                "role": "tool",
                "tool_call_id": tc_id,
                "content": _make_feedback(result_papers, new_count, error_msg),
            })

        if done:
            break
