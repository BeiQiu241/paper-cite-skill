"""Main pipeline for the simplified codex-only papercite."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Any, Optional

import yaml

_HERE = Path(__file__).parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from modules.citation_locator import build_citation_task, validate_citation_result
from modules.codex_backend import CodexTaskRunner
from modules.codex_task_specs import build_search_task, validate_search_result
from modules.docx_marker import annotate_docx
from modules.docx_reader import get_full_text, read_docx
from modules.llm_ranker import build_review_task, validate_review_result
from modules.paper_analyzer import build_analysis_task, extract_abstract, validate_analysis_result
from modules.reference_formatter import append_references_to_docx, generate_reference_list, save_references_txt
from modules.text_cleaner import clean_paragraphs, merge_short_paragraphs


DEFAULT_CONFIG: dict[str, Any] = {
    "execution": {"backend": "codex"},
    "selection": {"cn_count": 5, "en_count": 5},
    "annotation": {
        "highlight_color": "none",
        "style": "inline_numeric",
    },
    "output": {
        "reference_format": "GBT7714-2015",
        "save_references_txt": True,
        "save_annotated_docx": False,
        "write_to_docx": True,
    },
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge dictionaries."""
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(config_path: Optional[str] = None) -> dict[str, Any]:
    """Load config and merge it with built-in defaults."""
    path = Path(config_path) if config_path else (_HERE / "config.yaml")
    if not path.exists():
        return dict(DEFAULT_CONFIG)

    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise RuntimeError("Config YAML must contain an object at the top level.")
    return _deep_merge(DEFAULT_CONFIG, payload)


def _next_available_path(path: Path) -> Path:
    """Return a non-conflicting sibling path when a file is locked."""
    if not path.exists():
        return path

    index = 1
    while True:
        candidate = path.with_name(f"{path.stem}_{index}{path.suffix}")
        if not candidate.exists():
            return candidate
        index += 1


def _copy_with_fallback(src: Path, preferred_dst: Path) -> Path:
    """Copy a file, choosing a new name if the target is locked."""
    try:
        shutil.copy2(src, preferred_dst)
        return preferred_dst
    except PermissionError:
        alt = _next_available_path(preferred_dst)
        shutil.copy2(src, alt)
        return alt


def _build_output_paths(input_path: Path, output_dir: Optional[str]) -> tuple[Path, Path, Path]:
    """Return output paths for a document."""
    out_dir = Path(output_dir) if output_dir else input_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = input_path.stem
    annotated_path = out_dir / f"{stem}_annotated.docx"
    references_path = out_dir / f"{stem}_references.txt"
    final_path = out_dir / f"{stem}_final.docx"
    return annotated_path, references_path, final_path


def _resolve_reference_counts(
    selection_cfg: dict[str, Any],
    cn_count: Optional[int],
    en_count: Optional[int],
) -> tuple[int, int]:
    """Resolve Chinese and English reference counts with fast defaults."""
    selected_cn = int(cn_count if cn_count is not None else selection_cfg.get("cn_count", 5))
    selected_en = int(en_count if en_count is not None else selection_cfg.get("en_count", 5))

    if selected_cn < 0 or selected_en < 0:
        raise RuntimeError("Chinese and English reference counts must be 0 or greater.")
    if selected_cn == 0 and selected_en == 0:
        raise RuntimeError("Chinese and English reference counts cannot both be 0.")

    return selected_cn, selected_en


def run_pipeline(
    docx_path: str,
    config_path: Optional[str] = None,
    output_dir: Optional[str] = None,
    cn_count: Optional[int] = None,
    en_count: Optional[int] = None,
    backend: str = "codex",
    task_dir: Optional[str] = None,
    ref_format: Optional[str] = None,
    codex_state: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Run the simplified codex-only pipeline."""
    if str(backend).lower() != "codex":
        raise RuntimeError("The simplified build only supports the `codex` backend.")

    cfg = load_config(config_path)
    selection_cfg = cfg.get("selection", {})
    annotation_cfg = cfg.get("annotation", {})
    output_cfg = cfg.get("output", {})

    selected_cn, selected_en = _resolve_reference_counts(selection_cfg, cn_count, en_count)
    reference_format = str(ref_format or output_cfg.get("reference_format", "GBT7714-2015")).upper()
    save_annotated_docx = bool(output_cfg.get("save_annotated_docx", False))
    del task_dir

    input_path = Path(docx_path)
    annotated_path, references_path, final_path = _build_output_paths(input_path, output_dir)
    task_runner = CodexTaskRunner(codex_state)

    print(f"[1/8] Reading document: {input_path.name}")
    paragraphs = read_docx(str(input_path))
    print(f"  Paragraphs: {len(paragraphs)}")

    print("[2/8] Cleaning text")
    cleaned = merge_short_paragraphs(clean_paragraphs(paragraphs))
    full_text = get_full_text(cleaned)
    print(f"  Kept: {len(cleaned)} paragraphs")

    print("[3/8] Analyzing paper")
    abstract = extract_abstract(cleaned)
    analysis_text = abstract if len(abstract) >= 120 else full_text
    analysis = task_runner.resolve(
        "01-paper-analysis",
        build_analysis_task(analysis_text),
        validate_analysis_result,
    )

    print("[4/8] Searching literature")
    print(f"  Target references: CN {selected_cn} / EN {selected_en}")
    target_papers = max((selected_cn + selected_en) * 3, 20)
    candidates = task_runner.resolve(
        "02-literature-search",
        build_search_task(analysis, target_papers=target_papers),
        validate_search_result,
    )
    print(f"  Candidates: {len(candidates)}")

    print("[5/8] Selecting references")
    ranked = task_runner.resolve(
        "03-literature-review",
        build_review_task(candidates, analysis, selected_cn, selected_en),
        lambda result: validate_review_result(result, candidates, echo_logs=True),
    )
    references = generate_reference_list(ranked, fmt=reference_format)

    print("[6/8] Mapping citation positions")
    citation_positions = task_runner.resolve(
        "04-citation-positions",
        build_citation_task(cleaned, ranked),
        lambda result: validate_citation_result(result, cleaned, ranked, echo_logs=True),
    )
    print(f"  Positions: {len(citation_positions)}")

    print("[7/8] Writing cited document")
    cited_doc_path = annotated_path if save_annotated_docx else final_path
    try:
        annotate_docx(
            input_path=str(input_path),
            output_path=str(cited_doc_path),
            citation_positions=citation_positions,
            highlight_color=annotation_cfg.get("highlight_color", "none"),
        )
    except PermissionError:
        cited_doc_path = _next_available_path(cited_doc_path)
        annotate_docx(
            input_path=str(input_path),
            output_path=str(cited_doc_path),
            citation_positions=citation_positions,
            highlight_color=annotation_cfg.get("highlight_color", "none"),
        )
        if not save_annotated_docx:
            final_path = cited_doc_path
    except Exception as exc:
        print(f"  Citation insertion failed, copied original instead: {exc}")
        cited_doc_path = _copy_with_fallback(input_path, cited_doc_path)
        if not save_annotated_docx:
            final_path = cited_doc_path

    if save_annotated_docx:
        annotated_path = cited_doc_path
    else:
        final_path = cited_doc_path

    print("[8/8] Writing references")
    if output_cfg.get("save_references_txt", True):
        try:
            save_references_txt(references, str(references_path))
        except PermissionError:
            references_path = _next_available_path(references_path)
            save_references_txt(references, str(references_path))

    if output_cfg.get("write_to_docx", True) and references:
        doc_source = annotated_path if save_annotated_docx else final_path
        try:
            append_references_to_docx(str(doc_source), str(final_path), references)
        except PermissionError:
            final_path = _next_available_path(final_path)
            append_references_to_docx(str(doc_source), str(final_path), references)
        except Exception as exc:
            print(f"  Failed to append references, copied cited document instead: {exc}")
            final_path = _copy_with_fallback(doc_source, final_path)
    else:
        final_path = annotated_path if save_annotated_docx else final_path

    if not save_annotated_docx and annotated_path.exists():
        try:
            annotated_path.unlink()
        except OSError:
            pass

    output_files: dict[str, str] = {
        "references_txt": str(references_path),
        "final_docx": str(final_path),
    }
    if save_annotated_docx and annotated_path.exists():
        output_files["annotated"] = str(annotated_path)

    return {
        "analysis": analysis,
        "ranked_papers": ranked,
        "citation_positions": citation_positions,
        "references": references,
        "selected_counts": {"cn": selected_cn, "en": selected_en},
        "output_files": output_files,
        "backend": "codex",
        "task_dir": None,
    }
