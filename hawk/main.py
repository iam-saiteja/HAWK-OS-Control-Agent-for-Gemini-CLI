from __future__ import annotations

import os
import re
import sys
import time

from .agent import ask_agent, reset_chat, verify_progress
from .bridge import Bridge
from .executor import execute_action
from .hawk import get_screen_state


_BLIND_BOOTSTRAP_PATTERNS = (
    re.compile(r"\bopen\b", re.IGNORECASE),
    re.compile(r"\blaunch\b", re.IGNORECASE),
)


def _should_use_blind_bootstrap(task: str, turn: int) -> bool:
    """Allow launch-style tasks to continue even if first perception is empty."""
    if turn != 0:
        return False

    return any(pattern.search(task) for pattern in _BLIND_BOOTSTRAP_PATTERNS)


def _is_debug_enabled() -> bool:
    return os.getenv("HAWK_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}


def run(
    task: str,
    max_turns: int = 25,
    settle_seconds: float = 0.8,
    focus_delay: float = 3.0,
    empty_retry_delay: float = 0.8,
    empty_retry_limit: int = 5,
) -> None:
    bridge = Bridge()
    action_history: list[str] = []
    turn = 0

    reset_chat()
    print(f"[hawk] Task: {task}")
    print(f"[hawk] Focusing target window in {focus_delay:.1f} seconds...")
    time.sleep(focus_delay)

    while turn < max_turns:
        window_title, elements = get_screen_state()

        if not elements and _should_use_blind_bootstrap(task, turn):
            if _is_debug_enabled():
                print("[hawk] No elements detected yet; continuing with blind bootstrap for launch-style task.")
        else:
            empty_retries = 0
            while not elements and empty_retries < empty_retry_limit:
                print(f"[hawk] No elements found, retrying... ({empty_retries + 1}/{empty_retry_limit})")
                time.sleep(empty_retry_delay)
                window_title, elements = get_screen_state()
                empty_retries += 1

        if not elements:
            snapshot = "WINDOW: Unknown\\nDIFF: No elements detected. (Blind typing allowed: type 0 <text>)"
        elif turn == 0:
            snapshot = bridge.format_snapshot(elements, window_title)
        else:
            snapshot = bridge.format_diff(elements, window_title)

        if turn > 0 and turn % 5 == 0:
            status = verify_progress(task, action_history, snapshot)
            print(f"[hawk] Verifier says: {status}")
            if status == "DONE":
                print("[hawk] Task complete (verified).")
                break
            if status == "REPLAN":
                print("[hawk] Replanning with full snapshot.")
                snapshot = bridge.format_snapshot(elements, window_title)

        action = ask_agent(snapshot, task)
        print(f"[{turn}] {action}")
        action_history.append(action)

        should_continue = execute_action(action, bridge.get_elements())
        if not should_continue:
            print("[hawk] Task complete.")
            break

        if action.lower().startswith("launch "):
            print("[hawk] Waiting for launched app to fully render...")
            time.sleep(2.5)

        turn += 1
        time.sleep(settle_seconds)

    if turn >= max_turns:
        print(f"[hawk] Reached max turns ({max_turns}). Stopping.")


if __name__ == "__main__":
    run(" ".join(sys.argv[1:]) or "open notepad and type hello world")
