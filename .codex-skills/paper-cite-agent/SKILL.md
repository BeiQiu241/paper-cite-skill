---
name: paper-cite-agent
description: Run the existing paper reference automation project at D:\py projects\paper-agent\paper-cite-agent to analyze a .docx thesis or paper, search Chinese and English literature, identify citation locations, annotate the Word file, and generate a references list. Use when Codex needs to operate, troubleshoot, or adjust this workflow for Word papers, automatic reference search, citation insertion, reference formatting, or misplaced annotations. Default to the internal `codex` backend so Codex fills the four reasoning-heavy steps directly instead of relying on external model APIs.
---

# Paper Cite Agent

## Use The Project

Use the existing project at `D:\py projects\paper-agent\paper-cite-agent` rather than rebuilding the workflow.
Work from that directory when running commands.
Treat `cli.py` as the primary entrypoint and `main.py` as the pipeline orchestrator.

## Prepare The Environment

Install dependencies with `pip install -r requirements-pip.txt` if the environment is missing packages.
Inspect `config.yaml` before running the pipeline.
Default to `--backend codex`.
Do not require a model provider or API key when using the `codex` backend.
Only use the `api` backend when the user explicitly asks for external model execution.
Do not print or expose secrets from `config.yaml` in the response.

## Run The Pipeline

Run the CLI with a Word document path and the `codex` backend:

```powershell
python cli.py "D:\path\to\paper.docx" --backend codex
```

Use `--task-dir` when you want a predictable request/response folder:

```powershell
python cli.py "D:\path\to\paper.docx" --backend codex --task-dir "D:\path\to\tasks"
```

Use options when the user asks for custom output or reference counts:

```powershell
python cli.py "D:\path\to\paper.docx" --backend codex --output "D:\path\to\out" --cn 5 --en 5 --format APA
```

Expect these sibling outputs unless `--output` overrides them:
- `<stem>_annotated.docx`
- `<stem>_references.txt`
- `<stem>_final.docx`

Expect these task files in `--task-dir` or the default `<stem>_codex_tasks` directory:
- `01-paper-analysis.request.json` and `.response.json`
- `02-literature-search.request.json` and `.response.json`
- `03-literature-review.request.json` and `.response.json`
- `04-citation-positions.request.json` and `.response.json`

If the CLI exits with the message `Codex task input prepared`, read the generated request file, write the matching response JSON, and rerun the same command. Continue until the pipeline completes.

## Troubleshoot By Module

Inspect these files first when the workflow misbehaves:
- `main.py`: step order, output paths, backend routing, and top-level exception handling.
- `modules/text_cleaner.py`: filtering of directory pages, headers, footers, and reference sections.
- `modules/citation_locator.py`: paragraph selection rules and paragraph index validation.
- `modules/docx_marker.py`: Word write-back, highlighting, appended citations, and comments.
- `modules/reference_formatter.py`: formatted reference output and final reference list writing.
- `modules/codex_backend.py`: task request/response handoff for the `codex` backend.
- `modules/codex_task_specs.py`: structured task schemas for Codex-managed literature search.

Check paragraph index consistency before debugging model quality. If cleaned paragraphs are re-numbered but Word write-back uses original paragraph order, citations can land in the table of contents or headings.
If a `codex` run stalls, verify that the expected `.response.json` file exists and matches the request schema before rerunning.

## Respond Clearly

Summarize the exact command you ran, the files produced, and any blockers.
If the run fails, report the failing pipeline step and the module most likely responsible.
Prefer the `codex` backend by default and only mention the `api` backend when it is relevant to the user's request.
Prefer minimal fixes that preserve the existing workflow and output naming.
