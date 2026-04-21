from __future__ import annotations

import re
import subprocess
from typing import Dict

import pyautogui

SYSTEM_PROMPT = """You control a Windows computer. Each turn you receive the current screen state.

Respond with EXACTLY ONE action on a single line:
  click <id>
  type <id> <text>
  key <combo>
  scroll <id> <up|down>
  done

Nothing else. No explanation. One line only."""

_ACTION_PATTERN = re.compile(r"^(click\s+\d+|type\s+\d+\s+.+|key\s+[^\s]+|scroll\s+\d+\s+(up|down)|done)$", re.IGNORECASE)


def ask_gemini(snapshot: str, task: str, cli_command: str = "gemini") -> str:
    prompt = f"{SYSTEM_PROMPT}\n\nTask: {task}\n\nScreen:\n{snapshot}"
    result = subprocess.run([cli_command, "-p", prompt], capture_output=True, text=True)

    action = (result.stdout or "").strip().splitlines()[0] if result.stdout else ""
    if not _ACTION_PATTERN.match(action):
        return "done"
    return action


def execute_action(action: str, elements: Dict[int, dict]) -> bool:
    parts = action.strip().split()
    if not parts:
        return False

    cmd = parts[0].lower()

    if cmd == "click" and len(parts) >= 2:
        el_id = int(parts[1])
        el = elements.get(el_id)
        if el:
            pyautogui.click(el["x"], el["y"])

    elif cmd == "type" and len(parts) >= 3:
        el_id = int(parts[1])
        text = " ".join(parts[2:])
        el = elements.get(el_id)
        if el:
            pyautogui.click(el["x"], el["y"])
            pyautogui.typewrite(text, interval=0.03)

    elif cmd == "key" and len(parts) >= 2:
        combo = parts[1]
        keys = combo.split("+")
        if len(keys) == 1:
            pyautogui.press(keys[0])
        else:
            pyautogui.hotkey(*keys)

    elif cmd == "scroll" and len(parts) >= 3:
        el_id = int(parts[1])
        direction = parts[2].lower()
        el = elements.get(el_id)
        if el:
            amount = -300 if direction == "down" else 300
            pyautogui.scroll(amount, x=el["x"], y=el["y"])

    elif cmd == "done":
        return False

    return True
