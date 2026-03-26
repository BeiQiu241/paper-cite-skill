"""Agent Pipeline：完整的论文参考文献检索流程。"""

import os
import sys
from pathlib import Path
from typing import Optional

import yaml

# 确保 paper-cite-agent 目录在路径中
_HERE = Path(__file__).parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from modules.docx_reader import read_docx, get_full_text
from modules.text_cleaner import clean_paragraphs, merge_short_paragraphs
from modules.paper_analyzer import analyze_paper, extract_abstract
from modules.llm_search import llm_search_literature
from modules.ranking import score_literature
from modules.citation_locator import locate_citation_positions_llm, locate_citation_positions_rule
from modules.docx_marker import annotate_docx
from modules.reference_formatter import (
    generate_reference_list,
    save_references_txt,
    append_references_to_docx,
)
from utils.embeddings import EmbeddingModel


def load_config(config_path: Optional[str] = None) -> dict:
    """加载配置文件。"""
    if config_path is None:
        config_path = _HERE / "config.yaml"
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}


def run_pipeline(
    docx_path: str,
    config_path: Optional[str] = None,
    use_llm_citation: bool = True,
    output_dir: Optional[str] = None,
    cn_count: Optional[int] = None,
    en_count: Optional[int] = None,
) -> dict:
    """
    执行完整的 Agent Pipeline。

    参数：
        docx_path: 输入 Word 文件路径
        config_path: 配置文件路径（可选）
        use_llm_citation: 是否使用 LLM 识别引用位置（True）或规则匹配（False）
        output_dir: 输出目录（默认与输入文件同目录）

    返回结果字典。
    """
    cfg = load_config(config_path)
    anthropic_cfg = cfg.get("anthropic", {})
    env_cfg = cfg.get("env", {})
    search_cfg = cfg.get("search", {})
    ranking_cfg = cfg.get("ranking", {})
    annotation_cfg = cfg.get("annotation", {})
    output_cfg = cfg.get("output", {})

    model = anthropic_cfg.get("model", "claude-opus-4-6")
    api_key = (
        anthropic_cfg.get("api_key")
        or env_cfg.get("ANTHROPIC_AUTH_TOKEN")
        or env_cfg.get("ANTHROPIC_API_KEY")
        or os.environ.get("ANTHROPIC_AUTH_TOKEN")
        or os.environ.get("ANTHROPIC_API_KEY")
    )
    base_url = (
        env_cfg.get("ANTHROPIC_BASE_URL")
        or os.environ.get("ANTHROPIC_BASE_URL")
        or None
    )
    timeout_raw = (
        env_cfg.get("API_TIMEOUT_MS")
        or os.environ.get("API_TIMEOUT_MS")
        or None
    )
    try:
        timeout_ms = int(timeout_raw) if timeout_raw else None
    except (TypeError, ValueError):
        timeout_ms = None

    # 统一设置环境变量，兼容 Anthropic SDK 默认读取逻辑。
    if api_key:
        os.environ["ANTHROPIC_API_KEY"] = api_key
        os.environ["ANTHROPIC_AUTH_TOKEN"] = api_key
    if base_url:
        os.environ["ANTHROPIC_BASE_URL"] = base_url

    input_path = Path(docx_path)
    if output_dir:
        out_dir = Path(output_dir)
    else:
        out_dir = input_path.parent

    stem = input_path.stem
    annotated_path = out_dir / f"{stem}_annotated.docx"
    references_path = out_dir / f"{stem}_references.txt"
    final_path = out_dir / f"{stem}_final.docx"

    print(f"\n{'='*60}")
    print(f"  paper-cite-agent 启动")
    print(f"  输入文件: {input_path.name}")
    print(f"{'='*60}\n")

    # ── 步骤 1：读取 Word 文档 ────────────────────────────────
    print("▶ [1/8] 读取 Word 文档...")
    paragraphs = read_docx(str(input_path))
    print(f"  读取到 {len(paragraphs)} 个段落")

    # ── 步骤 2：文本预处理 ────────────────────────────────────
    print("\n▶ [2/8] 文本预处理...")
    cleaned = clean_paragraphs(paragraphs)
    cleaned = merge_short_paragraphs(cleaned)
    full_text = get_full_text(cleaned)
    print(f"  清洗后保留 {len(cleaned)} 个段落，共 {len(full_text)} 字符")

    # ── 步骤 3：LLM 分析论文 ──────────────────────────────────
    print("\n▶ [3/8] 论文理解（LLM）...")
    abstract = extract_abstract(cleaned)
    analysis_text = abstract if len(abstract) > 200 else full_text
    analysis = analyze_paper(
        analysis_text,
        model=model,
        api_key=api_key,
        base_url=base_url,
        timeout_ms=timeout_ms,
    )

    field_zh = analysis.get("field_zh", "")
    kw_zh = analysis.get("keywords_zh", [])
    print(f"  研究领域: {analysis.get('field', 'Unknown')}"
          + (f"（{field_zh}）" if field_zh else ""))
    print(f"  英文关键词: {', '.join(analysis.get('keywords', []))}")
    print(f"  中文关键词: {', '.join(kw_zh)}")
    print(f"  摘要: {analysis.get('summary', '')[:120]}...")

    # ── 步骤 4：LLM 自主学术文献搜索 ─────────────────────────────
    print("\n▶ [4/8] LLM 自主搜索学术文献（中英双语）...")

    cr_email = search_cfg.get("crossref_email", "")
    target_papers = search_cfg.get("max_results", 8) * 4  # 候选池约为 top_k 的 4 倍

    candidates = llm_search_literature(
        paper_analysis=analysis,
        model=model,
        api_key=api_key,
        base_url=base_url,
        timeout_ms=timeout_ms,
        target_papers=max(target_papers, 24),
        crossref_email=cr_email or None,
    )

    # ── 步骤 5：文献排序与过滤 ────────────────────────────────
    print("\n▶ [5/8] 文献排序与筛选...")
    embedding_model = EmbeddingModel()
    top_k = ranking_cfg.get("top_k", 5)
    threshold = ranking_cfg.get("similarity_threshold", 0.1)

    # cn_count / en_count：CLI 参数优先，其次 config，最后按 top_k 各取一半
    _cn = cn_count if cn_count is not None else ranking_cfg.get("cn_count")
    _en = en_count if en_count is not None else ranking_cfg.get("en_count")
    if _cn is None and _en is None:
        # 兼容旧配置：top_k 中约 55% 中文
        _cn = round(top_k * 0.55)
        _en = top_k - _cn

    ranked = score_literature(
        candidates,
        analysis,
        top_k=top_k,
        cn_count=_cn,
        en_count=_en,
        similarity_threshold=threshold,
        embedding_model=embedding_model,
    )

    if not ranked:
        print("  ⚠ 未找到相关文献，建议检查关键词或网络连接")
        ranked = candidates[:top_k] if candidates else []

    cn_rec = sum(1 for p in ranked if p.get("source", "").endswith("_cn") or p.get("lang") == "zh")
    print(f"  筛选出 {len(ranked)} 篇推荐文献（中国机构/中文 {cn_rec} 篇 / 英文 {len(ranked)-cn_rec} 篇）：")
    for i, paper in enumerate(ranked, 1):
        score = paper.get("_score", 0)
        year = paper.get("year", "n.d.")
        lang_tag = "[中]" if paper.get("source", "").endswith("_cn") or paper.get("lang") == "zh" else "[EN]"
        print(f"  {i}. {lang_tag} [{score:.3f}] ({year}) {paper['title'][:65]}")

    # ── 步骤 6：引用位置识别 ──────────────────────────────────
    print("\n▶ [6/8] 识别引用位置...")
    if use_llm_citation:
        try:
            citation_positions = locate_citation_positions_llm(
                cleaned,
                model=model,
                api_key=api_key,
                base_url=base_url,
                timeout_ms=timeout_ms,
            )
        except Exception as e:
            print(f"  LLM 引用识别失败: {e}，回退到规则匹配")
            citation_positions = locate_citation_positions_rule(cleaned)
    else:
        citation_positions = locate_citation_positions_rule(cleaned)

    print(f"  找到 {len(citation_positions)} 处需要引用的位置")

    # ── 步骤 7：Word 标注 ─────────────────────────────────────
    print("\n▶ [7/8] 标注 Word 文档...")
    highlight_color = annotation_cfg.get("highlight_color", "yellow")
    add_comments = annotation_cfg.get("add_comments", True)

    try:
        annotate_docx(
            input_path=str(input_path),
            output_path=str(annotated_path),
            citation_positions=citation_positions,
            ranked_papers=ranked,
            highlight_color=highlight_color,
            add_comments=add_comments,
        )
    except Exception as e:
        print(f"  ⚠ 标注失败: {e}")
        import shutil
        shutil.copy(str(input_path), str(annotated_path))

    # ── 步骤 8：生成参考文献列表 ──────────────────────────────
    print("\n▶ [8/8] 生成参考文献列表...")
    ref_format = output_cfg.get("reference_format", "APA")
    references = generate_reference_list(ranked, fmt=ref_format)

    if output_cfg.get("save_references_txt", True):
        # 对全部候选也评分（用于排序输出），score 已在 ranked 里；candidates 没有 _score
        save_references_txt(
            references,
            str(references_path),
            all_candidates=candidates,
            fmt=ref_format,
        )

    if output_cfg.get("write_to_docx", True) and ranked:
        try:
            append_references_to_docx(
                doc_path=str(annotated_path),
                output_path=str(final_path),
                references=references,
                papers=ranked,
            )
        except Exception as e:
            print(f"  ⚠ 写入 Word 失败: {e}")
            import shutil
            shutil.copy(str(annotated_path), str(final_path))
    else:
        import shutil
        shutil.copy(str(annotated_path), str(final_path))

    # ── 完成 ───────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("  ✅ 完成！")
    print(f"\n  📄 标注文档: {annotated_path.name}")
    print(f"  📋 参考文献: {references_path.name}")
    print(f"  📝 最终文档: {final_path.name}")
    print(f"\n  推荐参考文献列表 ({ref_format})：")
    for ref in references:
        print(f"  • {ref}")
    print(f"{'='*60}\n")

    return {
        "analysis": analysis,
        "ranked_papers": ranked,
        "citation_positions": citation_positions,
        "references": references,
        "output_files": {
            "annotated": str(annotated_path),
            "references_txt": str(references_path),
            "final_docx": str(final_path),
        },
    }
