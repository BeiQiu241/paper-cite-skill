"""Word 标注模块：高亮段落并添加 Word 原生批注（边栏气泡）。"""

from datetime import datetime, timezone
from typing import List, Dict, Any

import lxml.etree as etree
from docx import Document
from docx.opc.part import Part
from docx.opc.packuri import PackURI
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.shared import RGBColor

# ── Word XML 命名空间 ────────────────────────────────────────────────────────

_W  = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
_W14 = 'http://schemas.microsoft.com/office/word/2010/wordml'

_COMMENTS_CT  = ('application/vnd.openxmlformats-officedocument'
                 '.wordprocessingml.comments+xml')
_COMMENTS_REL = ('http://schemas.openxmlformats.org/officeDocument/2006/'
                 'relationships/comments')

_HIGHLIGHT_MAP = {
    "yellow": "yellow", "green": "green", "cyan": "cyan",
    "magenta": "magenta", "blue": "blue", "red": "red",
}


def _w(tag: str) -> str:
    return f'{{{_W}}}{tag}'


# ── 高亮 ─────────────────────────────────────────────────────────────────────

def _highlight_para(para, color: str = "yellow"):
    """高亮段落中的所有 run。"""
    val = _HIGHLIGHT_MAP.get(color, "yellow")
    for run in para.runs:
        if run.text.strip():
            rPr = run._r.get_or_add_rPr()
            hl = OxmlElement("w:highlight")
            hl.set(qn("w:val"), val)
            rPr.append(hl)


# ── Word 原生批注 ─────────────────────────────────────────────────────────────

def _build_comments_xml(comments: List[Dict]) -> bytes:
    """
    构建 word/comments.xml 的完整 XML bytes。

    comments: [{"id": int, "author": str, "text": str}, ...]
    """
    nsmap = {'w': _W}
    root = etree.Element(_w('comments'), nsmap=nsmap)

    date_str = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

    for c in comments:
        cmt = etree.SubElement(root, _w('comment'))
        cmt.set(_w('id'),     str(c['id']))
        cmt.set(_w('author'), c.get('author', 'paper-cite-agent'))
        cmt.set(_w('date'),   date_str)

        p = etree.SubElement(cmt, _w('p'))

        # 段落样式
        pPr = etree.SubElement(p, _w('pPr'))
        pStyle = etree.SubElement(pPr, _w('pStyle'))
        pStyle.set(_w('val'), 'CommentText')

        # 批注编号 run（Word 规范要求）
        r0 = etree.SubElement(p, _w('r'))
        r0Pr = etree.SubElement(r0, _w('rPr'))
        r0Style = etree.SubElement(r0Pr, _w('rStyle'))
        r0Style.set(_w('val'), 'CommentReference')
        r0t = etree.SubElement(r0, _w('t'))
        r0t.text = str(c['id'])

        # 批注正文 run
        r = etree.SubElement(p, _w('r'))
        t = etree.SubElement(r, _w('t'))
        t.text = c['text']
        t.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')

    return etree.tostring(root, xml_declaration=True,
                          encoding='UTF-8', standalone=True)


def _attach_comments_part(doc, comments: List[Dict]):
    """将 comments.xml 写入 docx 包并建立关联。"""
    blob = _build_comments_xml(comments)
    doc_part = doc.part
    try:
        # 已存在则替换 blob
        cp = doc_part.part_related_by(_COMMENTS_REL)
        cp._blob = blob
    except KeyError:
        cp = Part(PackURI('/word/comments.xml'), _COMMENTS_CT,
                  blob, doc_part.package)
        doc_part.relate_to(cp, _COMMENTS_REL)


def _insert_comment_ref(para_xml, cid: int):
    """在段落 XML 末尾插入 commentRangeStart/End 和 commentReference。"""
    s = str(cid)

    # commentRangeStart：插到 pPr 后面（若有），否则插到最前
    cs = etree.Element(_w('commentRangeStart'))
    cs.set(_w('id'), s)
    pPr = para_xml.find(_w('pPr'))
    pos = (list(para_xml).index(pPr) + 1) if pPr is not None else 0
    para_xml.insert(pos, cs)

    # commentRangeEnd
    ce = etree.SubElement(para_xml, _w('commentRangeEnd'))
    ce.set(_w('id'), s)

    # commentReference run
    ref_run = etree.SubElement(para_xml, _w('r'))
    ref_rPr = etree.SubElement(ref_run, _w('rPr'))
    ref_style = etree.SubElement(ref_rPr, _w('rStyle'))
    ref_style.set(_w('val'), 'CommentReference')
    ref = etree.SubElement(ref_run, _w('commentReference'))
    ref.set(_w('id'), s)


# ── 主入口 ────────────────────────────────────────────────────────────────────

def annotate_docx(
    input_path: str,
    output_path: str,
    citation_positions: List[Dict[str, Any]],
    ranked_papers: List[Dict[str, Any]],
    highlight_color: str = "yellow",
    add_comments: bool = True,
    references: List[str] = None,
) -> str:
    """
    在 Word 文档中：
      1. 黄色高亮需要引用的段落原文
      2. 段落末尾直接写入 GB/T 7714 格式引用（灰色斜体）
      3. Word 原生批注气泡保留引用理由

    参数：
        references: 已格式化的参考文献列表（与 ranked_papers 等长），
                    用于在行内写入完整的格式化引用。若为 None 则退回旧格式。
    """
    doc = Document(input_path)

    # ── 建立 paragraph_index → position_info 映射 ────────────
    index_map: Dict[int, Dict] = {
        pos['paragraph_index']: pos
        for pos in citation_positions
        if 'paragraph_index' in pos
    }

    # ── 遍历段落标注 ──────────────────────────────────────────
    comments_to_add: List[Dict] = []
    comment_id = 1
    para_counter = 0

    for para in doc.paragraphs:
        if not para.text.strip():
            continue
        para_counter += 1

        pos_info = index_map.get(para_counter)
        if pos_info is None:
            continue

        # 1. 黄色高亮原文
        _highlight_para(para, highlight_color)

        # 2. 构建引用标签（优先使用 GB/T 7714 格式化字符串）
        cite_indices = pos_info.get('cite_indices') or []
        labels = []
        for idx in cite_indices:
            if isinstance(idx, int):
                if references and 0 <= idx < len(references):
                    labels.append(references[idx])
                elif 0 <= idx < len(ranked_papers):
                    paper = ranked_papers[idx]
                    year = str(paper.get('year', '') or 'n.d.')
                    labels.append(f"({year}) {paper.get('title', '')}")

        cite_str = '；'.join(labels) if labels else '（见参考文献列表）'

        # 3. 在段落末尾内联写入引用文献（灰色斜体，不高亮，和正文区分）
        cite_run = para.add_run(f"  {cite_str}")
        cite_run.font.color.rgb = RGBColor(0x60, 0x60, 0x60)
        cite_run.font.italic = True

        # 4. 理由保留为 Word 原生批注气泡（优先使用 LLM 审查理由）
        reason = pos_info.get('review_reason') or pos_info.get('reason', '')
        if add_comments and reason:
            comments_to_add.append({
                'id': comment_id,
                'author': 'paper-cite-agent',
                'text': f"引用理由：{reason}",
            })
            _insert_comment_ref(para._p, comment_id)
            comment_id += 1

    # ── 将 comments.xml 写入 docx 包 ─────────────────────────
    if comments_to_add:
        _attach_comments_part(doc, comments_to_add)

    print(f"  [Marker] 已标注 {para_counter} 段，引用位置 {len(index_map)} 处")
    doc.save(output_path)
    return output_path
