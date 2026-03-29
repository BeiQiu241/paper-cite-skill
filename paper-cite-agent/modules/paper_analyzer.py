"""论文理解模块：使用 Claude 提取研究领域、关键词、核心问题与摘要。"""

import json
from typing import Dict, Any, List, Optional

import anthropic


def analyze_paper(
    full_text: str,
    model: str = "claude-opus-4-6",
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    timeout_ms: Optional[int] = None,
) -> Dict[str, Any]:
    """
    使用 Claude 分析论文内容，返回结构化信息。

    返回格式：
    {
        "field": str,           # 研究领域
        "keywords": [str],      # 关键词列表（英文）
        "summary": str,         # 核心内容摘要
        "core_problem": str,    # 核心问题/研究目标
        "methods": [str],       # 使用的主要方法
        "search_queries": [str] # 建议的学术搜索关键词组合
    }
    """
    client_kwargs: Dict[str, Any] = {}
    if api_key:
        client_kwargs["api_key"] = api_key
    if base_url:
        client_kwargs["base_url"] = base_url
    if timeout_ms:
        client_kwargs["timeout"] = timeout_ms / 1000.0
    client = anthropic.Anthropic(**client_kwargs)

    # 截取前 8000 字符以控制 token 用量
    text_excerpt = full_text[:8000]

    system_prompt = """You are an academic research assistant. Analyze the provided paper text and extract structured information.
Always respond with valid JSON only, no additional text."""

    user_prompt = f"""Analyze the following academic paper text and extract key information.

Paper text:
{text_excerpt}

Respond ONLY with a JSON object in this exact format:
{{
    "field": "the research field (e.g., Computer Vision, Natural Language Processing, etc.)",
    "field_zh": "研究领域的中文名称（如：自然语言处理、计算机视觉）",
    "keywords": ["English keyword1", "English keyword2", "English keyword3", "keyword4", "keyword5"],
    "keywords_zh": ["中文关键词1", "中文关键词2", "中文关键词3", "关键词4", "关键词5"],
    "summary": "2-3 sentence summary of the core content and contributions",
    "core_problem": "the main research problem or objective",
    "methods": ["method1", "method2"],
    "search_queries": [
        "English query 1 for academic search",
        "English query 2 for academic search",
        "English query 3 for academic search"
    ],
    "search_queries_zh": [
        "中文检索词组合1",
        "中文检索词组合2",
        "中文检索词组合3"
    ]
}}

Rules:
- search_queries: English only, specific enough to find relevant papers on Google Scholar / Semantic Scholar
- search_queries_zh: Chinese only, suitable for CNKI/万方/维普 style searches, use core Chinese academic terms
- field_zh and keywords_zh must be standard Chinese academic terminology
- field should be a standard academic discipline name in English"""

    print("  [LLM] 正在分析论文内容...")

    response = client.messages.create(
        model=model,
        max_tokens=2048,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    # 提取文本内容
    text_content = "".join(
        block.text for block in response.content if block.type == "text"
    )

    if not text_content.strip():
        raise RuntimeError(
            "[LLM] 论文分析失败：模型未返回任何文本内容（可能是 API 或模型配置问题）"
        )

    # 去除 markdown 代码块
    import re as _re
    text_stripped = text_content.strip()
    if text_stripped.startswith("```"):
        text_stripped = _re.sub(r"^```[a-z]*\n?", "", text_stripped)
        text_stripped = _re.sub(r"\n?```$", "", text_stripped.strip()).strip()

    try:
        result = json.loads(text_stripped)
    except (json.JSONDecodeError, ValueError) as e:
        raise RuntimeError(
            f"[LLM] 论文分析失败：JSON 解析错误 — {e}\n"
            f"模型原始输出：\n{text_content[:500]}"
        ) from e

    # 校验必要字段
    for required in ("field", "keywords", "search_queries"):
        if required not in result:
            raise RuntimeError(
                f"[LLM] 论文分析失败：返回 JSON 缺少必要字段 '{required}'\n"
                f"实际返回：{list(result.keys())}"
            )

    return result


def extract_abstract(paragraphs: List[Dict[str, Any]]) -> str:
    """尝试从段落中提取摘要部分。"""
    abstract_lines = []
    in_abstract = False

    for para in paragraphs:
        text = para["text"].lower().strip()
        if text in ("abstract", "摘要"):
            in_abstract = True
            continue
        if in_abstract:
            # 遇到下一个主要章节标题则停止
            if para["is_heading"] and para["level"] <= 2:
                break
            abstract_lines.append(para["text"])
            if len(" ".join(abstract_lines)) > 1500:
                break

    return " ".join(abstract_lines)
