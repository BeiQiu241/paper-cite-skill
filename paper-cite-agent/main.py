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
from modules.llm_ranker import llm_review_literature
from modules.citation_locator import locate_citation_positions_llm
from modules.docx_marker import annotate_docx
from modules.reference_formatter import (
    generate_reference_list,
    save_references_txt,
    append_references_to_docx,
)


def _next_available_path(path: Path) -> Path:
    """Return a non-conflicting sibling path: name_1.ext, name_2.ext, ..."""
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    i = 1
    while True:
        candidate = parent / f"{stem}_{i}{suffix}"
        if not candidate.exists():
            return candidate
        i += 1


def _copy_with_fallback(src: Path, preferred_dst: Path) -> Path:
    """Copy file, and if destination is locked, retry with a new filename."""
    import shutil

    try:
        shutil.copy(str(src), str(preferred_dst))
        return preferred_dst
    except PermissionError:
        alt = _next_available_path(preferred_dst)
        print(f"  [IO] 目标文件被占用，改为写入: {alt.name}")
        shutil.copy(str(src), str(alt))
        return alt


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
    output_dir: Optional[str] = None,
    cn_count: Optional[int] = None,
    en_count: Optional[int] = None,
) -> dict:
    """
    执行完整的 Agent Pipeline。

    参数：
        docx_path: 输入 Word 文件路径
        config_path: 配置文件路径（可选）
        output_dir: 输出目录（默认与输入文件同目录）

    返回结果字典。
    """
    cfg = load_config(config_path)
    env_cfg = cfg.get("env", {})
    search_cfg = cfg.get("search", {})
    ranking_cfg = cfg.get("ranking", {})
    annotation_cfg = cfg.get("annotation", {})
    output_cfg = cfg.get("output", {})

    # ── 模型提供商配置 ────────────────────────────────────────
    provider_name = cfg.get("model_provider", "")
    provider_cfg = cfg.get("model_providers", {}).get(provider_name, {})
    model = cfg.get("model", "claude-opus-4-6")
    base_url = (
        provider_cfg.get("base_url")
        or env_cfg.get("ANTHROPIC_BASE_URL")
        or os.environ.get("ANTHROPIC_BASE_URL")
        or None
    )

    # API Key：优先读 OPENAI_API_KEY（linkapi 使用 OpenAI 鉴权），其次 Anthropic
    api_key = (
        env_cfg.get("OPENAI_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or env_cfg.get("ANTHROPIC_AUTH_TOKEN")
        or env_cfg.get("ANTHROPIC_API_KEY")
        or os.environ.get("ANTHROPIC_AUTH_TOKEN")
        or os.environ.get("ANTHROPIC_API_KEY")
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

    # 统一写入环境变量，供各子模块 SDK 读取
    if api_key:
        os.environ["OPENAI_API_KEY"] = api_key
        os.environ["ANTHROPIC_API_KEY"] = api_key
        os.environ["ANTHROPIC_AUTH_TOKEN"] = api_key
    if base_url:
        os.environ["ANTHROPIC_BASE_URL"] = base_url

    # 检测是否为 OpenAI 兼容接口（tool calling 使用 OpenAI function calling 格式）
    openai_compat = bool(provider_cfg.get("requires_openai_auth") or provider_cfg.get("wire_api"))

    if provider_name:
        print(f"  [Config] 模型提供商: {provider_name} | 模型: {model} | Base URL: {base_url}")
        print(f"  [Config] OpenAI 兼容模式: {'开启' if openai_compat else '关闭'}")

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
        openai_compat=openai_compat,
    )

    # ── 步骤 5：LLM 审查与筛选 ───────────────────────────────────
    print("\n▶ [5/8] LLM 审查候选文献...")

    _cn = cn_count if cn_count is not None else ranking_cfg.get("cn_count", 5)
    _en = en_count if en_count is not None else ranking_cfg.get("en_count", 5)

    ranked = llm_review_literature(
        candidates=candidates,
        paper_analysis=analysis,
        cn_count=_cn,
        en_count=_en,
        model=model,
        api_key=api_key,
        base_url=base_url,
        timeout_ms=timeout_ms,
    )
    ref_format = output_cfg.get("reference_format", "GBT7714")
    references = generate_reference_list(ranked, fmt=ref_format)

    # ── 步骤 6：引用位置识别 ──────────────────────────────────
    print("\n▶ [6/8] 识别引用位置（LLM）...")
    citation_positions = locate_citation_positions_llm(
        paragraphs=cleaned,
        ranked_papers=ranked,
        model=model,
        api_key=api_key,
        base_url=base_url,
        timeout_ms=timeout_ms,
    )

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
            references=references,
        )
    except PermissionError:
        alt_annotated = _next_available_path(annotated_path)
        print(f"  [IO] ????????????: {alt_annotated.name}")
        annotate_docx(
            input_path=str(input_path),
            output_path=str(alt_annotated),
            citation_positions=citation_positions,
            ranked_papers=ranked,
            highlight_color=highlight_color,
            add_comments=add_comments,
            references=references,
        )
        annotated_path = alt_annotated
    except Exception as e:
        print(f"  ? ????: {e}")
        annotated_path = _copy_with_fallback(input_path, annotated_path)

    # ── 步骤 8：生成参考文献列表 ──────────────────────────────
    print("\n▶ [8/8] 生成参考文献列表...")
    if output_cfg.get("save_references_txt", True):
        # ?????????????????score ?? ranked ??candidates ?? _score
        try:
            save_references_txt(
                references,
                str(references_path),
                all_candidates=candidates,
                selected_papers=ranked,
                fmt=ref_format,
            )
        except PermissionError:
            alt_refs = _next_available_path(references_path)
            print(f"  [IO] ??????????????: {alt_refs.name}")
            save_references_txt(
                references,
                str(alt_refs),
                all_candidates=candidates,
                selected_papers=ranked,
                fmt=ref_format,
            )
            references_path = alt_refs

    if output_cfg.get("write_to_docx", True) and ranked:
        try:
            append_references_to_docx(
                doc_path=str(annotated_path),
                output_path=str(final_path),
                references=references,
                papers=ranked,
            )
        except PermissionError:
            alt_final = _next_available_path(final_path)
            print(f"  [IO] ????????????: {alt_final.name}")
            append_references_to_docx(
                doc_path=str(annotated_path),
                output_path=str(alt_final),
                references=references,
                papers=ranked,
            )
            final_path = alt_final
        except Exception as e:
            print(f"  ? ?? Word ??: {e}")
            final_path = _copy_with_fallback(annotated_path, final_path)
    else:
        final_path = _copy_with_fallback(annotated_path, final_path)

    # ── 完成 ───────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("  ✅ 完成！")
    print(f"\n  📄 标注文档: {annotated_path.name}")
    print(f"  📋 参考文献: {references_path.name}")
    print(f"  📝 最终文档: {final_path.name}")
    cn_reviewed = sum(
        1 for p in ranked
        if p.get("source", "").endswith("_cn") or p.get("lang") == "zh"
    )
    en_reviewed = len(ranked) - cn_reviewed
    print(
        f"\n  [LLM审查] 选出 {len(ranked)} 篇（中文 {cn_reviewed} 篇 / 英文 {en_reviewed} 篇）"
    )
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
