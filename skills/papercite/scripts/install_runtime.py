"""Install and verify the bundled Paper Cite runtime dependencies."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


SCRIPT_ROOT = Path(__file__).resolve().parent
REQUIREMENTS_PATH = SCRIPT_ROOT / "requirements.txt"
RUNNER_PATH = SCRIPT_ROOT / "run_papercite.py"


def build_parser() -> argparse.ArgumentParser:
    """Build the installer CLI."""
    parser = argparse.ArgumentParser(
        prog="install_runtime",
        description="Install dependencies for the bundled Paper Cite runtime.",
    )
    parser.add_argument(
        "--skip-verify",
        action="store_true",
        help="Install dependencies without running the wrapper help check.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Install requirements and optionally verify the wrapper entrypoint."""
    args = build_parser().parse_args(argv)

    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS_PATH)]
    )

    if not args.skip_verify:
        subprocess.check_call([sys.executable, str(RUNNER_PATH), "--help"])

    print("Paper Cite runtime is ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
