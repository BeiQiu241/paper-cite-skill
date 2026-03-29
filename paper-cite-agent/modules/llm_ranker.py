"""LLM 文献审查模块：让模型从候选文献中挑选最相关的中英文参考文献。"""

import json
import re
from typing import List, Dict, Any, Optional

import anthropic


def llm_review_literature(
    candidates: List[Dict[str, Any]],
    paper_analysis: Dict[str, Any],
    cn_count: int = 5,
    en_count: int = 5,
    model: str = "claude-opus-4-6",
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    timeout_ms: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    使用 LLM 审查所有候选文献，挑选最符合论文主题的参考文献。

    参数：
        candidates     : 搜索得到的全部候选文献
        paper_analysis : analyze_paper() 返回的分析结果
        cn_count       : 需要的中文/中国机构论文数量
        en_count       : 需要的英文论文数量

    返回：经 LLM 审查后选出的文献列表（含原始字段）。
    """
    if not candidates:
        raise RuntimeError("[LLM审查] 候选文献为空，无法进行审查")

    client_kwargs: Dict[str, Any] = {}
    if api_key:
        client_kwargs["api_key"] = api_key
    if base_url:
        client_kwargs["base_url"] = base_url
    if timeout_ms:
        import httpx
        client_kwargs["timeout"] = httpx.Timeout(timeout_ms / 1000.0)
    client = anthropic.Anthropic(**client_kwargs)

    # ── 构建候选文献摘要列表 ──────────────────────────────────────
    _CN_SOURCES = {"openalex_cn", "openalex_zh"}

    def _is_cn(p: Dict) -> bool:
        return (
            p.get("source", "") in _CN_SOURCES
            or p.get("lang") == "zh"
            or bool(re.search(r'[\u4e00-\u9fff]', p.get("title", "")))
        )

    lines = []
    for i, p in enumerate(candidates):
        lang_tag = "中文" if _is_cn(p) else "英文"
        journal = p.get("journal", "")
        year = p.get("year", "")
        abstract = (p.get("abstract") or "")[:120].replace("\n", " ")
        source = p.get("source", "")
        lines.append(
            f"[{i}] [{lang_tag}] ({year}) {p['title']}\n"
            f"    期刊: {journal or '未知'}  来源: {source}\n"
            f"    摘要: {abstract}"
        )

    candidates_text = "\n\n".join(lines)

    # ── 构建提示词 ────────────────────────────────────────────────
    field = paper_analysis.get("field", "")
    field_zh = paper_analysis.get("field_zh", "")
    keywords = ", ".join(paper_analysis.get("keywords", []))
    keywords_zh = ", ".join(paper_analysis.get("keywords_zh", []))
    summary = (paper_analysis.get("summary") or "")[:400]
    core_problem = paper_analysis.get("core_problem", "")

    system_prompt = "你是专业的学术文献审查专家，擅长评估论文与参考文献的相关性。只输出 JSON，不输出其他内容。"

    user_prompt = f"""请从以下候选文献中，为目标论文挑选最合适的参考文献。

## 目标论文信息
- 研究领域：{field}（{field_zh}）
- 英文关键词：{keywords}
- 中文关键词：{keywords_zh}
- 核心问题：{core_problem}
- 摘要：{summary}

## 选择要求
- 中文论文（含中国机构发表的论文）：选 {cn_count} 篇
- 英文论文：选 {en_count} 篇
- 优先选择：与论文核心问题直接相关、方法或领域高度匹配的文献
- 避免选择：主题偏离、仅名称相似但内容无关的文献

## 候选文献列表（共 {len(candidates)} 篇）

{candidates_text}

## 输出格式
返回如下 JSON，selected 中按相关度从高到低排列：
{{
  "selected": [
    {{"index": 数字, "lang": "中文或英文", "reason": "一句话说明选择理由"}},
    ...
  ]
}}

只返回 JSON，不要任何其他文字。"""

    print(f"  [LLM审查] 正在审查 {len(candidates)} 篇候选文献...")

    response = client.messages.create(
        model=model,
        max_tokens=2048,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    text_content = "".join(
        block.text for block in response.content if block.type == "text"
    )

    if not text_content.strip():
        raise RuntimeError("[LLM审查] 模型未返回任何内容")

    # 去除 markdown 代码块
    text_stripped = text_content.strip()
    if text_stripped.startswith("```"):
        text_stripped = re.sub(r"^```[a-z]*\n?", "", text_stripped)
        text_stripped = re.sub(r"\n?```$", "", text_stripped.strip()).strip()

    try:
        result = json.loads(text_stripped)
    except (json.JSONDecodeError, ValueError) as e:
        raise RuntimeError(
            f"[LLM审查] JSON 解析失败: {e}\n原始输出:\n{text_content[:500]}"
        ) from e

    selected_items = result.get("selected", [])
    if not selected_items:
        raise RuntimeError("[LLM审查] 模型返回的 selected 列表为空")

    # ── 按 index 取回原始文献对象 ────────────────────────────────
    chosen = []
    for item in selected_items:
        idx = item.get("index")
        if idx is None or not (0 <= idx < len(candidates)):
            print(f"  [LLM审查] 跳过无效索引: {idx}")
            continue
        paper = dict(candidates[idx])
        paper["_review_reason"] = item.get("reason", "")
        paper["_lang_tag"] = item.get("lang", "")
        chosen.append(paper)

    cn_chosen = [p for p in chosen if _is_cn(p)]
    en_chosen = [p for p in chosen if not _is_cn(p)]
    print(
        f"  [LLM审查] 选出 {len(chosen)} 篇"
        f"（中文 {len(cn_chosen)} 篇 / 英文 {len(en_chosen)} 篇）"
    )
    for p in chosen:
        tag = p.get("_lang_tag", "")
        reason = p.get("_review_reason", "")
        print(f"  • [{tag}] ({p.get('year','')}) {p['title'][:60]}  — {reason}")

    return chosen
