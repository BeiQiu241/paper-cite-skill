"""Word 文档解析模块：提取段落文本与结构。"""

from typing import List, Dict, Any
from docx import Document


def read_docx(file_path: str) -> List[Dict[str, Any]]:
    """
    读取 Word 文档，返回段落列表。

    每个元素格式：
    {
        "index": int,          # 段落序号（从 1 开始）
        "text": str,           # 段落文本
        "style": str,          # 段落样式名称（如 Heading 1、Normal）
        "is_heading": bool,    # 是否为标题
        "level": int,          # 标题级别（0 表示非标题）
    }
    """
    doc = Document(file_path)
    paragraphs = []
    index = 1

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue

        style_name = para.style.name if para.style else "Normal"
        is_heading = style_name.startswith("Heading")
        level = 0
        if is_heading:
            try:
                level = int(style_name.split()[-1])
            except (ValueError, IndexError):
                level = 1

        paragraphs.append({
            "index": index,
            "text": text,
            "style": style_name,
            "is_heading": is_heading,
            "level": level,
        })
        index += 1

    return paragraphs


def get_full_text(paragraphs: List[Dict[str, Any]]) -> str:
    """将段落列表合并为完整文本。"""
    return "\n\n".join(p["text"] for p in paragraphs)
