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

Use `scripts/install_runtime.py` when you want an explicit setup step:

```powershell
python "<skill-dir>\scripts\install_runtime.py"
```

Use `scripts/install_and_run.ps1` when you want one command that installs dependencies and immediately runs the workflow:

```powershell
powershell -ExecutionPolicy Bypass -File "<skill-dir>\scripts\install_and_run.ps1" "D:\path\to\paper.docx" --backend codex
```

If the user runs `scripts/run_papercite.py` directly without a setup step, the wrapper should auto-install missing `python-docx` and `pyyaml` dependencies on first run.
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

## Install From GitHub

For Codex CLI users, prefer a one-line install plus dependency bootstrap command after they publish the repo:

```powershell
$codexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME ".codex" }; python (Join-Path $codexHome "skills/.system/skill-installer/scripts/install-skill-from-github.py") --repo "<owner>/<repo>" --path "skills/paper-cite-agent"; python (Join-Path $codexHome "skills/paper-cite-agent/scripts/install_runtime.py")
```

For Codex Desktop users who provide a GitHub link, install the skill from that link, run `scripts/install_runtime.py`, and verify the wrapper with `--help` before handing the workflow back to the user.

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
