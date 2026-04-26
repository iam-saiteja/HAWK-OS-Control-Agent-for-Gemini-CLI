from __future__ import annotations

import argparse
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

from hawk.gui import launch_gui
from hawk.main import run


_DEFAULT_TASK = "open notepad and type hello world"


def _parse_args(argv: list[str]) -> tuple[bool, str]:
    parser = argparse.ArgumentParser(description="HAWK desktop control agent")
    parser.add_argument("--gui", action="store_true", help="launch the Tkinter frontend")
    parser.add_argument("task", nargs="*", help="task to run in CLI mode or preload in the GUI")
    parsed = parser.parse_args(argv)
    return parsed.gui, " ".join(parsed.task).strip()


if __name__ == "__main__":
    use_gui, task = _parse_args(sys.argv[1:])
    if use_gui:
        launch_gui(task or _DEFAULT_TASK)
    else:
        run(task or _DEFAULT_TASK)
