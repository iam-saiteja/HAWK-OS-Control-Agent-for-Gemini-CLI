from __future__ import annotations

import time

import pyautogui
import pyperclip

pyautogui.FAILSAFE = True


def execute_action(action: str, elements: dict) -> bool:
    """Execute one action and return True to continue, False to stop."""
    parts = action.strip().split()
    if not parts:
        return True

    cmd = parts[0].lower()

    try:
        if cmd == "click":
            el = _get_element(parts, elements)
            if el:
                pyautogui.click(el["x"], el["y"])

        elif cmd == "type":
            if len(parts) >= 3 and parts[1] == "0":
                text = " ".join(parts[2:])
                time.sleep(0.2)
                pyperclip.copy(text)
                pyautogui.hotkey("ctrl", "v")
            else:
                el = _get_element(parts, elements)
                if el and len(parts) >= 3:
                    text = " ".join(parts[2:])
                    pyautogui.click(el["x"], el["y"])
                    time.sleep(0.15)
                    pyperclip.copy(text)
                    pyautogui.hotkey("ctrl", "v")

        elif cmd == "key":
            if len(parts) >= 2:
                keys = parts[1].split("+")
                if len(keys) == 1:
                    pyautogui.press(keys[0])
                else:
                    pyautogui.hotkey(*keys)

        elif cmd == "launch":
            if len(parts) >= 2:
                app_name = " ".join(parts[1:])
                pyautogui.press("win")
                time.sleep(0.5)
                pyperclip.copy(app_name)
                pyautogui.hotkey("ctrl", "v")
                time.sleep(0.5)
                pyautogui.press("enter")
                time.sleep(3.5)  # Wait for the heavy UI to open

        elif cmd == "scroll":
            el = _get_element(parts, elements)
            if el and len(parts) >= 3:
                direction = parts[2].lower()
                amount = -3 if direction == "down" else 3
                pyautogui.scroll(amount, x=el["x"], y=el["y"])

        elif cmd == "done":
            return False

    except Exception as exc:
        print(f"[executor] Error executing '{action}': {exc}")

    time.sleep(0.1)
    return True


def _get_element(parts: list[str], elements: dict) -> dict | None:
    """Safely resolve element ID from an action token list."""
    try:
        el_id = int(parts[1])
        if el_id in elements:
            return elements[el_id]
        print(f"[executor] Warning: element ID {el_id} not in current snapshot")
        return None
    except (IndexError, ValueError):
        print(f"[executor] Warning: invalid element ID in action: {parts}")
        return None
