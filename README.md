# papercite

`papercite` 是一个用于处理 `.docx` 论文的 Codex skill，可以自动生成：

- 文内引用标记
- 格式化参考文献列表
- 写回后的最终 Word 文档

`papercite` is a Codex skill for processing `.docx` papers and producing:

- in-text citation marks
- a formatted references list
- a final cited Word document

## 安装 / Install

仓库地址 / Repository:
`https://github.com/BeiQiu241/paper-cite-skill`

一键安装并补依赖 / One-line install plus dependency bootstrap:

```powershell
$codexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME ".codex" }; python (Join-Path $codexHome "skills/.system/skill-installer/scripts/install-skill-from-github.py") --repo BeiQiu241/paper-cite-skill --path skills/papercite; python (Join-Path $codexHome "skills/papercite/scripts/install_runtime.py")
```

## 运行 / Run

默认推荐 `fast` 模式，只会在需要时暂停一次，等待一个合并后的 JSON 响应。
Fast mode is the default and is optimized to stop at most once for one combined JSON response.

```powershell
python "<skill-dir>\scripts\run_papercite.py" "D:\path\to\paper.docx" --backend codex --mode fast
```

也可以安装后直接运行 / Or install and run in one step:

```powershell
powershell -ExecutionPolicy Bypass -File "<skill-dir>\scripts\install_and_run.ps1" "D:\path\to\paper.docx" --backend codex --mode fast
```

仅在调试旧流程时使用 `--mode interactive`。
Use `--mode interactive` only when debugging the legacy staged flow.

## 快速响应模板 / Compact Fast-Track JSON

当 fast 模式暂停时，优先返回下面这种短格式 JSON：
When fast mode pauses, prefer this compact JSON shape:

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

运行时仍兼容旧的长字段格式。
The runtime still accepts the older long-form keys for backward compatibility.

## Windows 续跑 / Windows Resume

Windows 下建议使用 `--codex-response-file`，不要把长 JSON 直接塞进命令行参数。
On Windows, prefer `--codex-response-file` instead of passing long JSON inline on the command line.

```powershell
python "<skill-dir>\scripts\run_papercite.py" "D:\path\to\paper.docx" --backend codex --mode fast --codex-state "<state-token>" --codex-step "01-fast-track-plan" --codex-response-file "D:\path\to\response.json"
```
