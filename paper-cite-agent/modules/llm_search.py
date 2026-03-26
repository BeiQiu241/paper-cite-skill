"""LLM 驱动的文献搜索：让模型自主决定搜索策略和查询词。"""

import json
import time
from typing import List, Dict, Any, Optional

import anthropic

from modules.scholar_search import (
    search_crossref,
    search_semantic_scholar,
    search_openalex,
)


# ─── 工具定义 ──────────────────────────────────────────────────────────────────

_TOOLS = [
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
            "搜索 OpenAlex 数据库。"
            "设 cn_only=true 时仅返回中国机构（country_code:cn）发表的论文，"
            "是获取中国研究成果的主要途径。查询词须为英文。"
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
                    "description": "true = 只返回中国机构发表的论文（获取中文研究时必须设为 true）",
                    "default": False,
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
) -> List[Dict[str, Any]]:
    """
    让 LLM 自主规划搜索策略，通过 tool_use 调用各学术数据库，
    返回去重后的候选文献列表。

    参数：
        paper_analysis : analyze_paper() 返回的分析结果
        model          : Claude 模型 ID
        api_key        : Anthropic API key
        base_url       : 代理 base URL（可选）
        timeout_ms     : 请求超时毫秒数
        max_iterations : 最大工具调用轮次
        target_papers  : 目标收集篇数（提示给模型）
        crossref_email : Crossref polite pool 邮箱（可选）
    """
    # ── 初始化客户端 ──────────────────────────────────────────────
    client_kwargs: Dict[str, Any] = {}
    if api_key:
        client_kwargs["api_key"] = api_key
    if base_url:
        client_kwargs["base_url"] = base_url
    if timeout_ms:
        import httpx
        client_kwargs["timeout"] = httpx.Timeout(timeout_ms / 1000.0)
    client = anthropic.Anthropic(**client_kwargs)

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

## 搜索策略要求
1. **目标**：收集约 {target_papers} 篇候选文献
2. **中英比例**：中国机构发表的论文占约 55%，英文论文约 45%
   - 获取中国机构论文：使用 search_openalex(cn_only=true)
   - 获取英文论文：使用 search_crossref 或 search_openalex(cn_only=false)
   - 中文关键词搜索：使用 search_semantic_scholar
3. **覆盖度**：对每个主要主题/关键词至少搜索一次，使用多样化查询词
4. **效率**：避免重复相同查询词，收集到足够文献后调用 finish_search

## 已有参考查询词（可参考修改）
- 英文：{queries_hint}
- 中文：{queries_zh_hint}
"""

    messages = [
        {"role": "user", "content": "请开始搜索与该论文相关的参考文献。"},
    ]

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

    # ── Agentic 循环 ──────────────────────────────────────────────
    for iteration in range(max_iterations):
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            system=system_prompt,
            tools=_TOOLS,
            messages=messages,
        )

        # 把助手回复加入对话历史
        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        done = False

        for block in response.content:
            if not hasattr(block, "type") or block.type != "tool_use":
                continue

            tool_name = block.name
            tool_input = block.input or {}
            print(f"  [LLM-Search] {tool_name}({json.dumps(tool_input, ensure_ascii=False, separators=(',',':'))})")

            # finish_search → 退出循环
            if tool_name == "finish_search":
                print(f"  [LLM-Search] 完成: {tool_input.get('summary', '')}")
                done = True
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": "搜索完成。",
                })
                break

            # 执行搜索工具
            result_papers: List[Dict] = []
            error_msg = ""
            try:
                if tool_name == "search_crossref":
                    result_papers = search_crossref(
                        tool_input["query"],
                        rows=min(int(tool_input.get("rows", 10)), 20),
                        email=crossref_email,
                    )
                elif tool_name == "search_semantic_scholar":
                    result_papers = search_semantic_scholar(
                        tool_input["query"],
                        limit=min(int(tool_input.get("limit", 10)), 20),
                    )
                elif tool_name == "search_openalex":
                    result_papers = search_openalex(
                        tool_input["query"],
                        limit=min(int(tool_input.get("limit", 10)), 20),
                        cn_only=bool(tool_input.get("cn_only", False)),
                    )
                time.sleep(0.3)
            except Exception as exc:
                error_msg = str(exc)
                print(f"  [LLM-Search]   ✗ {exc}")

            new_count = _add(result_papers)
            cn_total = sum(
                1 for p in all_papers
                if p.get("source", "").endswith("_cn") or p.get("lang") == "zh"
            )
            print(f"  [LLM-Search]   → 新增 {new_count} 篇 | 累计 {len(all_papers)} 篇（中国机构/中文 {cn_total}）")

            # 返回摘要给模型（避免 token 爆炸）
            sample = [
                {
                    "title": p["title"][:70],
                    "year": p.get("year"),
                    "citations": p.get("citations", 0),
                    "lang": p.get("lang", "en"),
                }
                for p in result_papers[:4]
            ]
            feedback = {
                "found": len(result_papers),
                "new_added": new_count,
                "total_collected": len(all_papers),
                "sample_titles": sample,
            }
            if error_msg:
                feedback["error"] = error_msg

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(feedback, ensure_ascii=False),
            })

        if done:
            break
        if response.stop_reason == "end_turn" and not tool_results:
            break
        if tool_results:
            messages.append({"role": "user", "content": tool_results})

    cn_count = sum(
        1 for p in all_papers
        if p.get("source", "").endswith("_cn") or p.get("lang") == "zh"
    )
    print(
        f"  [LLM-Search] 合计 {len(all_papers)} 篇"
        f"（中国机构/中文 {cn_count} 篇 / 其他 {len(all_papers)-cn_count} 篇）"
    )
    return all_papers
