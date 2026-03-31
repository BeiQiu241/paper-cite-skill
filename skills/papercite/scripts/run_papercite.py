"""Launch the bundled Paper Cite runtime from the installed skill folder."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


SCRIPT_ROOT = Path(__file__).resolve().parent
RUNTIME_ROOT = Path(__file__).resolve().parent / "papercite_runtime"
REQUIREMENTS_PATH = SCRIPT_ROOT / "requirements.txt"


def _ensure_runtime_dependencies() -> None:
    """Install first-run dependencies automatically when needed."""
    missing = []

    try:
        import docx  # noqa: F401
    except ModuleNotFoundError:
        missing.append("python-docx")

    try:
        import yaml  # noqa: F401
    except ModuleNotFoundError:
        missing.append("pyyaml")

    if not missing:
        return

    print(
        "Installing bundled runtime dependencies: "
        + ", ".join(missing),
        file=sys.stderr,
    )
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS_PATH)]
    )


_ensure_runtime_dependencies()

if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from cli import main  # type: ignore  # Imported from the bundled runtime path.


if __name__ == "__main__":
    raise SystemExit(main())
