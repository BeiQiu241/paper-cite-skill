$ErrorActionPreference = "Stop"

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = if ($env:PYTHON) { $env:PYTHON } else { "python" }

& $Python (Join-Path $ScriptRoot "install_runtime.py")
& $Python (Join-Path $ScriptRoot "run_papercite.py") @args
