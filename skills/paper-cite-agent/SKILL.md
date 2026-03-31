---
name: paper-cite-agent
description: Analyze a .docx thesis or paper, search Chinese and English literature, map citation positions, write citations back into Word, and generate a references list by using the bundled Paper Cite runtime. Use when Codex needs to run, troubleshoot, or adapt an automatic paper-citation workflow for Word documents, citation insertion, reference formatting, or misplaced annotations. Prefer the bundled `codex` backend and do not require external model APIs unless the user explicitly asks for them.
---

# Paper Cite Agent

## Use The Bundled Runtime

Use the skill's bundled runtime instead of any machine-specific project path.
Treat `scripts/run_papercite.py` as the only entrypoint.
Treat `scripts/papercite_runtime/main.py` as the pipeline orchestrator when debugging internals.

## Prepare The Environment

Install dependencies from the skill folder before the first run:

```powershell
python -m pip install -r "<skill-dir>\scripts\requirements.txt"
```

Use the bundled default config at `scripts/papercite_runtime/config.yaml` unless the user provides another config file.
Default to `--backend codex`.
Do not require or mention external API keys unless the user explicitly asks for a non-codex backend.

## Run The Pipeline

Run the wrapper script with a Word document path:

```powershell
python "<skill-dir>\scripts\run_papercite.py" "D:\path\to\paper.docx" --backend codex
```

Use options when the user asks for custom output or reference counts:

```powershell
python "<skill-dir>\scripts\run_papercite.py" "D:\path\to\paper.docx" --backend codex --output "D:\path\to\out" --cn 5 --en 5 --format APA
```

Expect these outputs unless `--output` overrides them:
- `<stem>_references.txt`
- `<stem>_final.docx`
- `<stem>_annotated.docx` only when config enables `save_annotated_docx`

## Handle Pending Codex Steps

If the wrapper exits with `Codex task input prepared`, it will print:
- `step: <step-name>`
- `state_token: <opaque-token>`
- a JSON payload between `request_json_begin` and `request_json_end`

Read that request JSON, produce the matching response JSON, and rerun the same command with the saved state token plus the completed step response. Use stdin for long JSON:

```powershell
Get-Content "D:\path\to\response.json" | python "<skill-dir>\scripts\run_papercite.py" "D:\path\to\paper.docx" --backend codex --codex-state "<state-token>" --codex-step "<step-name>" --codex-response-stdin
```

Repeat until the pipeline prints `Done`.

## Troubleshoot By Module

Inspect these files first when the workflow misbehaves:
- `scripts/papercite_runtime/main.py`: pipeline order, output paths, and top-level exception handling.
- `scripts/papercite_runtime/modules/text_cleaner.py`: filtering of table-of-contents text, headers, footers, and references.
- `scripts/papercite_runtime/modules/citation_locator.py`: paragraph selection rules and paragraph index validation.
- `scripts/papercite_runtime/modules/docx_marker.py`: Word write-back, highlighting, and appended citations.
- `scripts/papercite_runtime/modules/reference_formatter.py`: formatted reference output and final reference list writing.
- `scripts/papercite_runtime/modules/codex_backend.py`: pending-step state token and request/response handoff.
- `scripts/papercite_runtime/modules/codex_task_specs.py`: structured task schemas for literature search.

Check paragraph index consistency before blaming model quality. If cleaned paragraphs are re-numbered incorrectly, citations can land in a table of contents or heading instead of the target body paragraph.
If a resumed run fails, verify that the response JSON matches the pending step schema before rerunning.

## Respond Clearly

Summarize the exact command you ran, the files produced, and any blockers.
If the run fails, report the failing pipeline step and the module most likely responsible.
Prefer minimal fixes that preserve the existing output naming and the bundled runtime workflow.
