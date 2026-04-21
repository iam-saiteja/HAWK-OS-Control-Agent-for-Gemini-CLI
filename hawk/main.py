from __future__ import annotations

import sys
import time

from .agent import ask_agent, reset_chat, verify_progress
from .bridge import Bridge
from .executor import execute_action
from .hawk import get_screen_state


def run(task: str, max_turns: int = 25, settle_seconds: float = 0.8) -> None:
    bridge = Bridge()
    action_history: list[str] = []
    turn = 0

    reset_chat()
    print(f"[hawk] Task: {task}")
    print("[hawk] Focusing target window in 3 seconds...")
    time.sleep(3)

    while turn < max_turns:
        window_title, elements = get_screen_state()

        if not elements:
            print("[hawk] No elements found, retrying...")
            time.sleep(1)
            continue

        if turn == 0:
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

        turn += 1
        time.sleep(settle_seconds)

    if turn >= max_turns:
        print(f"[hawk] Reached max turns ({max_turns}). Stopping.")


if __name__ == "__main__":
    run(" ".join(sys.argv[1:]) or "open notepad and type hello world")
