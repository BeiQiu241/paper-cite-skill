"""文本预处理模块：清理无用内容，合并短段落，去重。"""

import re
from typing import List, Dict, Any


# 目录行的典型模式（"...1"、"……1"、"1." 加多个空格等）
_TOC_PATTERN = re.compile(r"^.{0,80}[\u2026\.]{3,}\s*\d+\s*$")

# 页眉页脚常见关键词
_HEADER_FOOTER_KEYWORDS = [
    "第.*页", "page", "©", "版权", "confidential", "draft",
]
_HEADER_FOOTER_RE = re.compile(
    "|".join(_HEADER_FOOTER_KEYWORDS), re.IGNORECASE
)

# 参考文献段落起始模式
_REFERENCE_SECTION_RE = re.compile(
    r"^(参考文献|references|bibliography|works cited)\s*$", re.IGNORECASE
)


def clean_paragraphs(
    paragraphs: List[Dict[str, Any]],
    min_length: int = 20,
) -> List[Dict[str, Any]]:
    """
    清理段落列表：
    1. 删除目录行
    2. 删除页眉页脚
    3. 删除参考文献段落之后的内容
    4. 去除过短/重复段落
    5. 重新编号
    """
    cleaned = []
    seen_texts = set()
    in_references = False

    for para in paragraphs:
        text = para["text"].strip()

        # 进入参考文献区后停止处理
        if _REFERENCE_SECTION_RE.match(text):
            in_references = True
        if in_references:
            continue

        # 跳过目录行
        if _TOC_PATTERN.match(text):
            continue

        # 跳过页眉页脚
        if len(text) < 80 and _HEADER_FOOTER_RE.search(text):
            continue

        # 跳过过短段落（非标题）
        if not para["is_heading"] and len(text) < min_length:
            continue

        # 去重
        if text in seen_texts:
            continue
        seen_texts.add(text)

        cleaned.append(para)

    # 重新编号
    for i, para in enumerate(cleaned, start=1):
        para["index"] = i

    return cleaned


def merge_short_paragraphs(
    paragraphs: List[Dict[str, Any]],
    min_length: int = 50,
) -> List[Dict[str, Any]]:
    """将过短的相邻非标题段落合并，减少碎片。"""
    if not paragraphs:
        return paragraphs

    merged = []
    buffer = None

    for para in paragraphs:
        if para["is_heading"]:
            if buffer:
                merged.append(buffer)
                buffer = None
            merged.append(para)
            continue

        if buffer is None:
            buffer = dict(para)
        elif len(buffer["text"]) < min_length:
            buffer["text"] += " " + para["text"]
        else:
            merged.append(buffer)
            buffer = dict(para)

    if buffer:
        merged.append(buffer)

    # 重新编号
    for i, para in enumerate(merged, start=1):
        para["index"] = i

    return merged
