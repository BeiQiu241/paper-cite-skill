"""Simple CLI entrypoint for the codex-only papercite."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_HERE = Path(__file__).parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from main import run_pipeline
from modules.codex_backend import CodexTaskPending, decode_state_token


def build_parser() -> argparse.ArgumentParser:
    """Build the command line parser."""
    parser = argparse.ArgumentParser(
        prog="papercite",
        description="Analyze a Word paper, map citation positions, and generate references.",
    )
    parser.add_argument("docx_file", type=Path, help="Path to the input .docx file.")
    parser.add_argument("-c", "--config", type=Path, help="Optional config YAML path.")
    parser.add_argument("-o", "--output", type=Path, help="Optional output directory.")
    parser.add_argument(
        "--cn",
        "--zh",
        "--cn-count",
        dest="cn",
        type=int,
        default=None,
        help="Target Chinese reference count.",
    )
    parser.add_argument(
        "--en",
        "--en-count",
        dest="en",
        type=int,
        default=None,
        help="Target English reference count.",
    )
    parser.add_argument(
        "-f",
        "--format",
        default=None,
        help="Reference format: GBT7714, APA, or IEEE.",
    )
    parser.add_argument(
        "--backend",
        default="codex",
        help="Only `codex` is supported in the simplified build.",
    )
    parser.add_argument(
        "--mode",
        choices=["fast", "interactive"],
        default=None,
        help="Pipeline mode. Default is `fast`; use `interactive` only for manual step injection/debugging.",
    )
    parser.add_argument(
        "--task-dir",
        type=Path,
        help="Deprecated. Kept only for backward compatibility and ignored.",
    )
    parser.add_argument(
        "--codex-state",
        default="",
        help="Opaque state token returned by a previous pending Codex step.",
    )
    parser.add_argument(
        "--codex-step",
        default="",
        help="Step name for the supplied Codex response, such as 01-paper-analysis.",
    )
    parser.add_argument(
        "--codex-response-json",
        default="",
        help="Inline JSON response for the supplied Codex step.",
    )
    parser.add_argument(
        "--codex-response-file",
        type=Path,
        default=None,
        help="Read the supplied Codex response JSON from a file.",
    )
    parser.add_argument(
        "--codex-response-stdin",
        action="store_true",
        help="Read the supplied Codex response JSON from stdin.",
    )
    return parser


def _validate_reference_counts(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """Validate optional Chinese and English reference counts."""
    if args.cn is not None and args.cn < 0:
        parser.error("--cn must be 0 or greater.")
    if args.en is not None and args.en < 0:
        parser.error("--en must be 0 or greater.")
    if args.cn == 0 and args.en == 0:
        parser.error("--cn and --en cannot both be 0.")


def _load_codex_state(args: argparse.Namespace) -> dict:
    """Decode prior state and inject one optional step response."""
    state = decode_state_token(args.codex_state)

    if not args.codex_step:
        if args.codex_response_json or args.codex_response_file or args.codex_response_stdin:
            raise RuntimeError("A Codex response was supplied without --codex-step.")
        return state

    response_sources = sum(
        bool(source)
        for source in (args.codex_response_json, args.codex_response_file, args.codex_response_stdin)
    )
    if response_sources > 1:
        raise RuntimeError(
            "Use only one of --codex-response-json, --codex-response-file, or --codex-response-stdin."
        )

    response_text = args.codex_response_json
    if args.codex_response_file:
        response_text = args.codex_response_file.read_text(encoding="utf-8-sig")
    elif args.codex_response_stdin:
        response_text = sys.stdin.read()

    if not response_text.strip():
        raise RuntimeError("A Codex response was requested but no JSON payload was provided.")

    try:
        state[args.codex_step] = json.loads(response_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Failed to parse Codex response JSON: {exc}") from exc
    return state


def main(argv: list[str] | None = None) -> int:
    """Run the simplified pipeline."""
    parser = build_parser()
    args = parser.parse_args(argv)
    _validate_reference_counts(parser, args)

    if not args.docx_file.exists():
        parser.error(f"File not found: {args.docx_file}")

    try:
        codex_state = _load_codex_state(args)
        result = run_pipeline(
            docx_path=str(args.docx_file),
            config_path=str(args.config) if args.config else None,
            output_dir=str(args.output) if args.output else None,
            cn_count=args.cn,
            en_count=args.en,
            backend=args.backend,
            task_dir=str(args.task_dir) if args.task_dir else None,
            ref_format=args.format,
            codex_state=codex_state,
            pipeline_mode=args.mode,
        )
    except CodexTaskPending as exc:
        print("Codex task input prepared.")
        print(f"step: {exc.step}")
        print(f"state_token: {exc.state_token}")
        print("request_json_begin")
        print(exc.request_json)
        print("request_json_end")
        return 2
    except KeyboardInterrupt:
        print("Interrupted.")
        return 1
    except Exception as exc:
        print(f"Run failed: {exc}", file=sys.stderr)
        return 1

    print("Done")
    for label, path in (result.get("output_files") or {}).items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
