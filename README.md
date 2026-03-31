# Paper Cite Agent

`paper-cite-agent` is a portable Codex skill for analyzing Word papers, selecting Chinese and English references, mapping citation positions, and writing citations plus references back into a `.docx` file.

## What It Does

- Analyze a thesis or paper from a `.docx` file
- Generate structured Codex tasks for paper analysis, literature search, literature review, and citation placement
- Resume the workflow step by step with JSON responses
- Produce a final cited Word document and a reference list

## Repository Layout

The publishable skill lives at [skills/paper-cite-agent](./skills/paper-cite-agent).

- `SKILL.md`: Codex skill instructions and workflow guidance
- `agents/openai.yaml`: UI metadata for the skill
- `scripts/run_papercite.py`: portable wrapper entrypoint
- `scripts/papercite_runtime/`: bundled runtime implementation
- `scripts/requirements.txt`: Python dependencies for the bundled runtime

## Install The Skill

After pushing this repository to GitHub, install the skill with Codex's GitHub installer:

```powershell
python "C:\Users\<your-user>\.codex\skills\.system\skill-installer\scripts\install-skill-from-github.py" --repo <owner>/<repo> --path skills/paper-cite-agent
```

Restart Codex after installation so the new skill is discovered.

## Install Runtime Dependencies

Install the Python dependencies from the installed skill folder before the first run:

```powershell
python -m pip install -r "<skill-dir>\scripts\requirements.txt"
```

## Run The Workflow

Use the bundled wrapper script:

```powershell
python "<skill-dir>\scripts\run_papercite.py" "D:\path\to\paper.docx" --backend codex
```

Example with custom output and reference counts:

```powershell
python "<skill-dir>\scripts\run_papercite.py" "D:\path\to\paper.docx" --backend codex --output "D:\path\to\out" --cn 5 --en 5 --format APA
```

## Resume Pending Steps

When the runtime prints `Codex task input prepared`, it also prints:

- `step`
- `state_token`
- a request JSON block

Create the matching response JSON and resume the same run:

```powershell
Get-Content "D:\path\to\response.json" | python "<skill-dir>\scripts\run_papercite.py" "D:\path\to\paper.docx" --backend codex --codex-state "<state-token>" --codex-step "<step-name>" --codex-response-stdin
```

Repeat until the tool prints `Done`.

## Outputs

The workflow writes these files next to the source document unless `--output` is provided:

- `<stem>_final.docx`
- `<stem>_references.txt`
- `<stem>_annotated.docx` when annotated output is enabled in config

## Notes

- The bundled runtime is optimized for the `codex` backend.
- No external model API is required for the default workflow.
- The skill is packaged to be portable and does not depend on machine-specific absolute paths.
