"""Helpers for resolving papercite fast-track requests with Codex CLI."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable


def _resolve_codex_command() -> str:
    """Resolve the Codex executable for non-interactive fast mode."""
    configured = os.environ.get("PAPERCITE_CODEX_BIN", "").strip()
    if configured:
        return configured

    for candidate in ("codex", "codex.exe"):
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return "codex"


def _build_prompt(request_payload: Dict[str, Any]) -> str:
    """Build a strict prompt for the internal fast-track solver."""
    return (
        "You are the internal fast-track solver for papercite.\n"
        "Solve the request and return JSON only.\n"
        "Do not wrap the answer in markdown or code fences.\n"
        "Do not ask clarifying questions.\n"
        "Do not write or modify files.\n"
        "Use available browsing/search capabilities when needed to find real academic references.\n"
        "Prefer the requested Chinese and English split, but prioritize relevance and credible sources if an exact split is impossible.\n"
        "Request payload:\n"
        f"{json.dumps(request_payload, ensure_ascii=False, indent=2)}\n"
    )


def _extract_json_block(text: str) -> Any:
    """Extract the first valid JSON object or array from mixed output."""
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char not in "{[":
            continue
        try:
            payload, _ = decoder.raw_decode(text[index:])
            return payload
        except json.JSONDecodeError:
            continue
    raise RuntimeError("Codex output did not contain valid JSON.")


def _run_exec_command(
    base_command: list[str],
    prompt: str,
    schema_path: Path,
    output_path: Path,
    workdir: Path,
) -> Any:
    """Run one Codex exec command and parse its JSON result."""
    command = list(base_command) + ["--output-schema", str(schema_path), "-o", str(output_path), "-"]
    completed = subprocess.run(
        command,
        input=prompt,
        text=True,
        capture_output=True,
        encoding="utf-8",
        cwd=str(workdir),
    )

    if completed.returncode != 0:
        details = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(
            "Codex fast mode failed. "
            f"Command: {' '.join(command)}. "
            f"Details: {details or 'No error details were returned.'}"
        )

    if output_path.exists():
        output_text = output_path.read_text(encoding="utf-8-sig").strip()
        if output_text:
            return json.loads(output_text)

    return _extract_json_block(completed.stdout)


def solve_fast_track_request(request_payload: Dict[str, Any], workdir: Path) -> Any:
    """Resolve one fast-track request end to end with Codex CLI."""
    codex_command = _resolve_codex_command()
    prompt = _build_prompt(request_payload)
    response_schema = request_payload.get("response_schema") or {"type": "object"}

    with tempfile.TemporaryDirectory(prefix="papercite-codex-") as temp_dir:
        temp_root = Path(temp_dir)
        schema_path = temp_root / "schema.json"
        output_path = temp_root / "output.json"
        schema_path.write_text(
            json.dumps(response_schema, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        command_variants: Iterable[list[str]] = (
            [codex_command, "exec", "--skip-git-repo-check", "--full-auto"],
            [codex_command, "exec", "--skip-git-repo-check"],
        )

        last_error: Exception | None = None
        for variant in command_variants:
            try:
                return _run_exec_command(variant, prompt, schema_path, output_path, workdir)
            except Exception as exc:
                last_error = exc

        raise RuntimeError(
            "Papercite fast mode could not invoke Codex CLI automatically. "
            "Set PAPERCITE_CODEX_BIN if Codex is installed in a non-standard location, "
            "or rerun with --mode interactive for legacy debugging."
        ) from last_error
