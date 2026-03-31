"""DOCX reading helpers."""

from __future__ import annotations

from typing import Any, Dict, List

from docx import Document


def read_docx(file_path: str) -> List[Dict[str, Any]]:
    """Read non-empty paragraphs from a Word document."""
    doc = Document(file_path)
    paragraphs: List[Dict[str, Any]] = []
    paragraph_index = 1

    for paragraph in doc.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue

        style_name = paragraph.style.name if paragraph.style else "Normal"
        is_heading = style_name.lower().startswith("heading")
        level = 0
        if is_heading:
            try:
                level = int(style_name.split()[-1])
            except (TypeError, ValueError, IndexError):
                level = 1

        paragraphs.append(
            {
                "index": paragraph_index,
                "text": text,
                "style": style_name,
                "is_heading": is_heading,
                "level": level,
            }
        )
        paragraph_index += 1

    return paragraphs


def get_full_text(paragraphs: List[Dict[str, Any]]) -> str:
    """Join cleaned paragraphs into a single text block."""
    return "\n\n".join(paragraph["text"] for paragraph in paragraphs)
