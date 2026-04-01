---
name: papercite
description: Analyze a .docx thesis or paper, search Chinese and English literature, map citation positions, write citations back into Word, and generate a references list by using the bundled papercite runtime. Use when Codex needs to run, troubleshoot, or adapt an automatic paper-citation workflow for Word documents, citation insertion, reference formatting, or misplaced annotations. Prefer the bundled `codex` backend and the default one-shot fast mode; only use the legacy interactive mode for debugging.
---

# papercite

## Interaction Policy

Default to fast execution with minimal confirmation.
Do not ask the user to confirm defaults one item at a time.
If the `.docx` path is clear, run immediately.
If the user does not specify reference counts, use the default split `--cn 5 --en 5` without asking.
If the user wants custom counts, ask once for both numbers together.
Only ask follow-up questions when a required file path is missing or ambiguous.

## Use The Bundled Runtime

Use the bundled runtime instead of any machine-specific project path.
Treat `scripts/run_papercite.py` as the only entrypoint.
Treat `scripts/papercite_runtime/main.py` as the pipeline orchestrator when debugging internals.

## Prepare The Environment

Use `scripts/install_runtime.py` when you want an explicit setup step:

```powershell
python "<skill-dir>\scripts\install_runtime.py"
```

Use `scripts/install_and_run.ps1` when you want one command that installs dependencies and immediately runs the workflow:

```powershell
powershell -ExecutionPolicy Bypass -File "<skill-dir>\scripts\install_and_run.ps1" "D:\path\to\paper.docx" --backend codex --mode fast
```

If the user runs `scripts/run_papercite.py` directly without a setup step, the wrapper should auto-install missing `python-docx` and `pyyaml` dependencies on first run.
Use the bundled default config at `scripts/papercite_runtime/config.yaml` unless the user provides another config file.
Default to `--backend codex --mode fast`.
Do not require or mention external API keys unless the user explicitly asks for a non-codex backend.

## Run The Pipeline

Run the wrapper script with a Word document path:

```powershell
python "<skill-dir>\scripts\run_papercite.py" "D:\path\to\paper.docx" --backend codex --mode fast
```

When the user wants a custom literature split, pass it directly:

```powershell
python "<skill-dir>\scripts\run_papercite.py" "D:\path\to\paper.docx" --backend codex --mode fast --cn 5 --en 8
```

Use options when the user asks for custom output or reference style:

```powershell
python "<skill-dir>\scripts\run_papercite.py" "D:\path\to\paper.docx" --backend codex --mode fast --output "D:\path\to\out" --cn 5 --en 5 --format APA
```

Expect these outputs unless `--output` overrides them:
- `<stem>_references.txt`
- `<stem>_final.docx`
- `<stem>_annotated.docx` only when config enables `save_annotated_docx`

## Fast-Track Behavior

Fast mode collapses the old multi-step workflow into one combined Codex task.
The runtime should usually stop at most once before it can finish.

If the wrapper exits with `Codex task input prepared`, it will print:
- `step: 01-fast-track-plan`
- `state_token: <opaque-token>`
- a JSON payload between `request_json_begin` and `request_json_end`

Read that request JSON, then return one combined response containing:
- `analysis`
- `refs`
- `cites`

Prefer this compact standard template:

```json
{
  "analysis": {
    "field": "Research field",
    "field_zh": "研究领域",
    "summary": "Short summary",
    "problem": "Core problem",
    "keywords": ["kw1", "kw2"],
    "keywords_zh": ["关键词1", "关键词2"],
    "methods": ["method 1", "method 2"],
    "queries": ["english search query"],
    "queries_zh": ["中文检索词"]
  },
  "refs": [
    {
      "title": "Paper title",
      "authors": ["Author A", "Author B"],
      "year": 2024,
      "journal": "Journal name",
      "doi": "10.xxxx/xxxx",
      "url": "https://example.com",
      "lang": "en",
      "reason": "Why this paper was selected"
    }
  ],
  "cites": [
    {
      "p": 12,
      "r": 0,
      "why": "Why this paragraph should cite the paper"
    }
  ]
}
```

The runtime also accepts the older long-form keys for backward compatibility.

Rerun the same command with the saved state token plus the completed step response.
Prefer the file-based path on Windows:

```powershell
python "<skill-dir>\scripts\run_papercite.py" "D:\path\to\paper.docx" --backend codex --mode fast --codex-state "<state-token>" --codex-step "01-fast-track-plan" --codex-response-file "D:\path\to\response.json"
```

Use `--mode interactive` only when debugging the legacy staged workflow.

## Ask For Counts Efficiently

If the user wants to choose how many references to use, ask once for both numbers together.
Use this wording pattern:

```text
How many Chinese papers and how many English papers do you want? If you do not specify, use the default split of 5 Chinese papers and 5 English papers.
```

Example mappings:
- `3 Chinese papers and 7 English papers` -> `--cn 3 --en 7`
- `English only, 8 papers` -> `--cn 0 --en 8`
- `Chinese only, 6 papers` -> `--cn 6 --en 0`
- no preference -> `--cn 5 --en 5`

## Install From GitHub

For Codex CLI users, prefer a one-line install plus dependency bootstrap command after they publish the repo:

```powershell
$codexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME ".codex" }; python (Join-Path $codexHome "skills/.system/skill-installer/scripts/install-skill-from-github.py") --repo "BeiQiu241/paper-cite-skill" --path "skills/papercite"; python (Join-Path $codexHome "skills/papercite/scripts/install_runtime.py")
```

For Codex Desktop users who provide `https://github.com/BeiQiu241/paper-cite-skill`, install the skill from path `skills/papercite`, run `scripts/install_runtime.py`, verify the wrapper with `--help`, and prefer the default fast mode.

## Troubleshoot By Module

Inspect these files first when the workflow misbehaves:
- `scripts/papercite_runtime/main.py`: pipeline order, output paths, and top-level exception handling.
- `scripts/papercite_runtime/modules/fast_path.py`: single-response fast-track request and validation.
- `scripts/papercite_runtime/modules/text_cleaner.py`: filtering of table-of-contents text, headers, footers, and references.
- `scripts/papercite_runtime/modules/citation_locator.py`: paragraph selection rules and paragraph index validation.
- `scripts/papercite_runtime/modules/docx_marker.py`: Word write-back, highlighting, and appended citations.
- `scripts/papercite_runtime/modules/reference_formatter.py`: formatted reference output and final reference list writing.
- `scripts/papercite_runtime/modules/codex_backend.py`: pending-step state token and request/response handoff.

Check paragraph index consistency before blaming model quality. If cleaned paragraphs are re-numbered incorrectly, citations can land in a table of contents or heading instead of the target body paragraph.
If a resumed run fails, verify that the response JSON matches the combined fast-track schema before rerunning.

## Respond Clearly

Summarize the exact command you ran, the files produced, and any blockers.
If the run fails, report the failing pipeline step and the module most likely responsible.
Prefer minimal fixes that preserve the existing output naming and the bundled runtime workflow.
