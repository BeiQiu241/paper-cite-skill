"""参考文献生成模块：生成 APA / IEEE 格式的参考文献列表。"""

from typing import List, Dict, Any
from docx import Document
from docx.shared import Pt


def format_apa(paper: Dict[str, Any], index: int) -> str:
    """生成 APA 格式引用。"""
    authors = paper.get("authors", [])
    year = paper.get("year", "n.d.")
    title = paper.get("title", "Unknown Title")
    doi = paper.get("doi", "")
    url = paper.get("url", "")

    # 作者格式：Last, F., & Last, F.
    formatted_authors = []
    for author in authors[:6]:
        parts = author.strip().split()
        if len(parts) >= 2:
            last = parts[-1]
            initials = ". ".join(p[0] for p in parts[:-1] if p) + "."
            formatted_authors.append(f"{last}, {initials}")
        else:
            formatted_authors.append(author)

    if len(authors) > 6:
        author_str = ", ".join(formatted_authors[:6]) + ", ... " + formatted_authors[-1]
    elif len(formatted_authors) > 1:
        author_str = ", ".join(formatted_authors[:-1]) + ", & " + formatted_authors[-1]
    elif formatted_authors:
        author_str = formatted_authors[0]
    else:
        author_str = "Unknown Author"

    ref = f"{author_str} ({year}). {title}."

    if doi:
        ref += f" https://doi.org/{doi}"
    elif url:
        ref += f" {url}"

    return ref


def format_ieee(paper: Dict[str, Any], index: int) -> str:
    """生成 IEEE 格式引用。"""
    authors = paper.get("authors", [])
    year = paper.get("year", "n.d.")
    title = paper.get("title", "Unknown Title")
    doi = paper.get("doi", "")
    url = paper.get("url", "")

    # 作者格式：F. Last
    formatted_authors = []
    for author in authors[:6]:
        parts = author.strip().split()
        if len(parts) >= 2:
            last = parts[-1]
            initials = ". ".join(p[0] for p in parts[:-1] if p) + "."
            formatted_authors.append(f"{initials} {last}")
        else:
            formatted_authors.append(author)

    if len(authors) > 6:
        author_str = ", ".join(formatted_authors[:6]) + " et al."
    else:
        author_str = ", ".join(formatted_authors)

    ref = f"[{index}] {author_str}, \"{title},\" {year}."

    if doi:
        ref += f" doi: {doi}."
    elif url:
        ref += f" [Online]. Available: {url}"

    return ref


def generate_reference_list(
    papers: List[Dict[str, Any]],
    fmt: str = "APA",
) -> List[str]:
    """生成完整参考文献列表。"""
    references = []
    for i, paper in enumerate(papers, start=1):
        if fmt.upper() == "IEEE":
            ref = format_ieee(paper, i)
        else:
            ref = format_apa(paper, i)
        references.append(ref)
    return references


def save_references_txt(
    references: List[str],
    output_path: str,
    all_candidates: List[Dict[str, Any]] = None,
    fmt: str = "APA",
):
    """
    保存参考文献列表到 txt 文件。

    - references      : 推荐文献（已格式化字符串，写入"推荐参考文献"区块）
    - all_candidates  : 全部候选文献原始列表，写入"全部候选文献"区块
    - fmt             : 全部候选的格式化格式
    """
    with open(output_path, "w", encoding="utf-8") as f:
        # ── 推荐文献 ──────────────────────────────────────────────
        f.write("【推荐参考文献】\n")
        f.write("=" * 60 + "\n\n")
        for ref in references:
            f.write(ref + "\n\n")

        # ── 全部候选 ──────────────────────────────────────────────
        if all_candidates:
            f.write("\n\n【全部候选文献（按相关度排序）】\n")
            f.write("=" * 60 + "\n")
            f.write(f"共 {len(all_candidates)} 篇\n\n")

            cn_papers = [p for p in all_candidates
                         if p.get("source", "").endswith("_cn") or p.get("lang") == "zh"]
            en_papers = [p for p in all_candidates
                         if not (p.get("source", "").endswith("_cn") or p.get("lang") == "zh")]

            if cn_papers:
                f.write(f"── 中国机构/中文文献（{len(cn_papers)} 篇）──\n\n")
                for i, paper in enumerate(cn_papers, 1):
                    ref = format_apa(paper, i) if fmt.upper() != "IEEE" else format_ieee(paper, i)
                    score = paper.get("_score")
                    score_str = f"  [相关度: {score:.3f}]" if score is not None else ""
                    f.write(f"{ref}{score_str}\n\n")

            if en_papers:
                f.write(f"── 英文文献（{len(en_papers)} 篇）──\n\n")
                for i, paper in enumerate(en_papers, 1):
                    ref = format_apa(paper, i) if fmt.upper() != "IEEE" else format_ieee(paper, i)
                    score = paper.get("_score")
                    score_str = f"  [相关度: {score:.3f}]" if score is not None else ""
                    f.write(f"{ref}{score_str}\n\n")

    print(f"  [References] 参考文献已保存至: {output_path}")


def append_references_to_docx(
    doc_path: str,
    output_path: str,
    references: List[str],
    papers: List[Dict[str, Any]],
):
    """将参考文献列表追加写入 Word 文档末尾。"""
    doc = Document(doc_path)

    doc.add_page_break()
    heading = doc.add_heading("推荐参考文献", level=1)

    for i, (ref, paper) in enumerate(zip(references, papers), start=1):
        para = doc.add_paragraph(ref)
        para.style = doc.styles["Normal"]

        # 添加链接信息
        url = paper.get("url", "")
        pdf_url = paper.get("pdf_url", "")
        if url or pdf_url:
            link_text = []
            if url:
                link_text.append(f"链接: {url}")
            if pdf_url:
                link_text.append(f"PDF: {pdf_url}")
            note_para = doc.add_paragraph("    " + " | ".join(link_text))
            note_para.runs[0].font.size = Pt(9)

        doc.add_paragraph()  # 空行分隔

    doc.save(output_path)
    print(f"  [References] 参考文献已写入文档: {output_path}")
