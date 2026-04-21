from __future__ import annotations

import sys
import time

from .bridge import Bridge
from .gemini_ext import ask_gemini, execute_action
from .hawk import get_screen_state


def run(task: str, max_turns: int = 20, settle_seconds: float = 0.5) -> None:
    bridge = Bridge()
    turn = 0

    while turn < max_turns:
        window_title, elements = get_screen_state()

        if turn == 0:
            snapshot, indexed = bridge.format_snapshot(elements, window_title)
        else:
            snapshot, indexed = bridge.format_diff(elements, window_title)

        action = ask_gemini(snapshot, task)
        print(f"[{turn}] {action}")

        should_continue = execute_action(action, indexed)
        if not should_continue:
            print("Task complete.")
            break

        turn += 1
        time.sleep(settle_seconds)


if __name__ == "__main__":
    run(" ".join(sys.argv[1:]) or "open notepad and type hello world")
