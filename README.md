# papercite

这是一个可安装的 Codex Skill，用于处理 `.docx` 论文/毕业设计文档，完成文献检索、引用定位、参考文献生成与写回。

## 安装

仓库地址：

`https://github.com/BeiQiu241/paper-cite-skill`

命令行一键安装并补依赖：

```powershell
$codexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME ".codex" }; python (Join-Path $codexHome "skills/.system/skill-installer/scripts/install-skill-from-github.py") --repo BeiQiu241/paper-cite-skill --path skills/papercite; python (Join-Path $codexHome "skills/papercite/scripts/install_runtime.py")
```

## 运行

```powershell
python "<skill-dir>\scripts\run_papercite.py" "D:\path\to\paper.docx" --backend codex
```

或直接安装并运行：

```powershell
powershell -ExecutionPolicy Bypass -File "<skill-dir>\scripts\install_and_run.ps1" "D:\path\to\paper.docx" --backend codex
```

## 桌面端

在 Codex Desktop 里直接提供这个 GitHub 链接，并说明安装路径是 `skills/papercite`，即可继续完成下载、安装、补依赖和验证。
