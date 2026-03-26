"""引用位置识别模块：找出论文中需要引用的句子。"""

import json
from typing import List, Dict, Any, Optional

import anthropic


# 基于规则的需要引用的句子模式（中英文）
_CITATION_PATTERNS_ZH = [
    "研究表明", "已有研究", "已有工作", "前人研究", "文献表明",
    "实验证明", "数据显示", "统计表明", "结果显示", "据报道",
    "有研究者", "相关研究", "现有方法", "传统方法", "经典方法",
    "等人提出", "等提出", "等研究", "学者认为", "学者指出",
    "研究发现", "调查显示", "报告显示", "指出", "认为",
    "广泛应用", "被广泛", "普遍认为", "目前研究", "现有研究",
    "如图所示", "表明", "证明", "提出了", "提出的",
]

_CITATION_PATTERNS_EN = [
    "previous work", "prior work", "related work", "studies have shown",
    "research has shown", "it has been shown", "it is well known",
    "according to", "proposed by", "introduced by", "based on",
    "existing methods", "traditional approaches", "state-of-the-art",
    "recent advances", "has been widely used", "widely adopted",
    "et al", "et al.", "were proposed", "was proposed", "have demonstrated",
    "has demonstrated", "showed that", "show that", "found that",
    "has been reported", "were reported", "is defined as", "are defined",
]


def locate_citation_positions_rule(
    paragraphs: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    基于规则匹配需要引用的句子（快速方案）。

    返回列表，每项格式：
    {
        "paragraph_index": int,
        "text": str,
        "reason": str,
    }
    """
    positions = []
    all_patterns = _CITATION_PATTERNS_ZH + _CITATION_PATTERNS_EN

    for para in paragraphs:
        if para.get("is_heading"):
            continue
        text = para["text"]
        text_lower = text.lower()

        for pattern in all_patterns:
            if pattern.lower() in text_lower:
                positions.append({
                    "paragraph_index": para["index"],
                    "text": text,
                    "reason": f"包含需引用模式: '{pattern}'",
                })
                break  # 每段只记录一次

    return positions


def locate_citation_positions_llm(
    paragraphs: List[Dict[str, Any]],
    model: str = "claude-opus-4-6",
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    timeout_ms: Optional[int] = None,
    max_paragraphs: int = 60,
) -> List[Dict[str, Any]]:
    """
    使用 LLM 识别需要引用的句子（精准方案）。
    """
    client_kwargs: Dict[str, Any] = {}
    if api_key:
        client_kwargs["api_key"] = api_key
    if base_url:
        client_kwargs["base_url"] = base_url
    if timeout_ms:
        client_kwargs["timeout"] = timeout_ms / 1000.0
    client = anthropic.Anthropic(**client_kwargs)

    # 只取非标题段落，限制数量
    body_paras = [p for p in paragraphs if not p.get("is_heading")][:max_paragraphs]

    para_text = "\n".join(
        f"[{p['index']}] {p['text']}" for p in body_paras
    )

    prompt = f"""You are an academic writing assistant. Identify paragraphs that NEED citations but likely don't have them yet.

Paragraphs to analyze:
{para_text}

Return a JSON array. Each element should have:
- "paragraph_index": the number in brackets (e.g., 3)
- "text": the paragraph text (first 100 chars)
- "reason": brief reason why it needs a citation (in Chinese)

Only include paragraphs that clearly need citations (claims about existing work, methods, statistics, established facts).
Return an empty array [] if none found.

RESPOND WITH VALID JSON ONLY."""

    print("  [LLM] 正在识别引用位置...")

    response = client.messages.create(
        model=model,
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}],
    )

    text_content = "".join(
        block.text for block in response.content if block.type == "text"
    )

    positions = _parse_json_array(text_content)
    if positions is None:
        print("  [LLM] 引用位置解析失败，回退到规则匹配")
        positions = locate_citation_positions_rule(paragraphs)

    return positions


def _parse_json_array(text: str):
    """
    从 LLM 输出中提取 JSON 数组，容错处理多种常见格式。
    返回 list 或 None（解析失败时）。
    """
    import re as _re

    text = text.strip()
    if not text:
        return None

    # 1. 去除 markdown 代码块
    if text.startswith("```"):
        text = _re.sub(r"^```[a-z]*\n?", "", text)
        text = _re.sub(r"\n?```$", "", text.strip())
        text = text.strip()

    # 2. 直接尝试解析
    try:
        result = json.loads(text)
        return result if isinstance(result, list) else None
    except json.JSONDecodeError:
        pass

    # 3. 提取第一个 [...] 块
    match = _re.search(r'\[.*?\]', text, _re.DOTALL)
    if match:
        try:
            result = json.loads(match.group())
            return result if isinstance(result, list) else None
        except json.JSONDecodeError:
            pass

    return None
