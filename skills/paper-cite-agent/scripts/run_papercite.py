"""Launch the bundled Paper Cite runtime from the installed skill folder."""

from __future__ import annotations

import sys
from pathlib import Path


RUNTIME_ROOT = Path(__file__).resolve().parent / "papercite_runtime"

if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from cli import main  # type: ignore  # Imported from the bundled runtime path.


if __name__ == "__main__":
    raise SystemExit(main())
