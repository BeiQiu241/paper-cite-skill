# papercite

`papercite` 是一个处理 `.docx` 论文的 Codex skill，可自动生成引文、参考文献列表，并写回最终 Word 文件。

仓库地址：
`https://github.com/BeiQiu241/paper-cite-skill`

一键安装并补依赖：

```powershell
$codexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME ".codex" }; python (Join-Path $codexHome "skills/.system/skill-installer/scripts/install-skill-from-github.py") --repo BeiQiu241/paper-cite-skill --path skills/papercite; python (Join-Path $codexHome "skills/papercite/scripts/install_runtime.py")
```

默认 `fast` 为单命令闭环执行：

```powershell
python "<skill-dir>\scripts\run_papercite.py" "D:\path\to\paper.docx" --backend codex --mode fast
```

只在调试旧流程时使用：

```powershell
python "<skill-dir>\scripts\run_papercite.py" "D:\path\to\paper.docx" --backend codex --mode interactive
```
