from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _venv_python_path() -> Path:
    root = Path(__file__).resolve().parent
    if os.name == "nt":
        return root / ".venv" / "Scripts" / "python.exe"
    return root / ".venv" / "bin" / "python"


def _rerun_with_venv_if_needed() -> None:
    """Use project venv python when this file is launched with a global interpreter."""
    venv_python = _venv_python_path()
    if not venv_python.exists():
        return

    try:
        current_python = Path(sys.executable).resolve()
        target_python = venv_python.resolve()
    except Exception:
        return

    if current_python == target_python:
        return

    script_path = str(Path(__file__).resolve())
    try:
        completed = subprocess.run([str(target_python), script_path, *sys.argv[1:]])
        raise SystemExit(completed.returncode)
    except KeyboardInterrupt:
        raise SystemExit(130)


_rerun_with_venv_if_needed()

from hawk.main import run


if __name__ == "__main__":
    task = " ".join(sys.argv[1:]) or "open notepad and type hello world"
    run(task)
