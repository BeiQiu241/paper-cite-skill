"""Word 标注模块：在文档中高亮标注需要引用的位置并添加批注。"""

from typing import List, Dict, Any, Optional
import re

from docx import Document
from docx.shared import RGBColor
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import lxml.etree as etree


def _hex_to_rgb(hex_color: str) -> RGBColor:
    """将 hex 颜色字符串转换为 RGBColor。"""
    hex_color = hex_color.lstrip("#")
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    return RGBColor(r, g, b)


# 高亮颜色映射（Word 支持有限的高亮颜色枚举）
_HIGHLIGHT_MAP = {
    "yellow": "yellow",
    "green": "green",
    "cyan": "cyan",
    "magenta": "magenta",
    "blue": "blue",
    "red": "red",
}


def _add_highlight_to_run(run, color: str = "yellow"):
    """为 run 添加高亮颜色。"""
    rPr = run._r.get_or_add_rPr()
    highlight = OxmlElement("w:highlight")
    highlight.set(qn("w:val"), _HIGHLIGHT_MAP.get(color, "yellow"))
    rPr.append(highlight)


def _add_comment_to_paragraph(para, comment_text: str, author: str = "paper-cite-agent"):
    """在段落末尾添加批注（Word XML 批注）。"""
    # 简化版：在段落末尾插入括号形式的内联标注
    # 完整 XML 批注实现需要操作 document.xml 的 comments 部分，较为复杂
    # 此处使用方括号批注作为替代，兼容性更好
    run = para.add_run(f"  【建议引用：{comment_text}】")
    run.font.color.rgb = RGBColor(0x80, 0x80, 0x80)
    run.font.italic = True
    run.font.size = None  # 继承段落字号


def annotate_docx(
    input_path: str,
    output_path: str,
    citation_positions: List[Dict[str, Any]],
    ranked_papers: List[Dict[str, Any]],
    highlight_color: str = "yellow",
    add_comments: bool = True,
) -> str:
    """
    在 Word 文档中标注引用位置。

    - 高亮需要引用的段落
    - 在段落末尾添加建议引用的文献信息

    返回输出文件路径。
    """
    doc = Document(input_path)

    # 提取所有引用位置文本，切分为有意义的片段用于匹配
    # 处理 merge_short_paragraphs 导致的合并文本问题
    def _extract_match_fragments(text: str, min_len: int = 15) -> list:
        """将文本切分为若干不重叠片段，每段可独立用于匹配。"""
        fragments = []
        # 按句号/换行切分
        import re
        parts = re.split(r'[。！？\n]', text)
        for p in parts:
            p = p.strip()
            if len(p) >= min_len:
                fragments.append(p[:80])
        # 如果切不出片段，直接用前80字符
        if not fragments and len(text) >= min_len:
            fragments.append(text[:80])
        return fragments

    citation_fragments: list = []
    for pos in citation_positions:
        for frag in _extract_match_fragments(pos.get("text", "")):
            citation_fragments.append(frag)

    # 准备推荐文献的简短标签
    paper_labels = []
    for i, paper in enumerate(ranked_papers[:5], start=1):
        authors = paper.get("authors", [])
        first_author = authors[0].split()[-1] if authors else "Unknown"
        year = paper.get("year", "n.d.")
        label = f"{first_author} et al., {year}"
        paper_labels.append(label)

    recommendation = "；".join(paper_labels) if paper_labels else "见参考文献列表"

    def _matches_any_fragment(para_text: str) -> bool:
        """判断段落文本是否与任意引用片段匹配。"""
        para_lower = para_text.lower()
        for frag in citation_fragments:
            frag_lower = frag.lower()
            # 精确子串匹配
            if frag_lower in para_lower:
                return True
            # 前缀匹配（应对轻微差异）
            if para_lower.startswith(frag_lower[:40]) and len(frag_lower) >= 20:
                return True
        return False

    # 遍历文档段落进行标注
    annotated_count = 0
    for para in doc.paragraphs:
        para_text = para.text.strip()
        if not para_text or len(para_text) < 10:
            continue

        should_annotate = _matches_any_fragment(para_text)

        if should_annotate:
            # 高亮段落中的所有 run
            for run in para.runs:
                if run.text.strip():
                    _add_highlight_to_run(run, highlight_color)

            # 添加内联批注
            if add_comments:
                _add_comment_to_paragraph(para, recommendation)

            annotated_count += 1

    print(f"  [Marker] 已标注 {annotated_count} 处引用位置")

    doc.save(output_path)
    return output_path
