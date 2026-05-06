from __future__ import annotations

import time

import pyautogui
import pyperclip

pyautogui.FAILSAFE = True


def _resolve_cursor_point(x: int, y: int) -> tuple[int, int]:
    width, height = pyautogui.size()

    if 0 <= x < width and 0 <= y < height:
        return x, y

    # Recover from common DPI-space mismatches before clamping.
    for scale in (1.25, 1.5, 1.75, 2.0):
        scaled_down = (int(x / scale), int(y / scale))
        if 0 <= scaled_down[0] < width and 0 <= scaled_down[1] < height:
            print(f"[executor] Adjusted point ({x},{y}) -> ({scaled_down[0]},{scaled_down[1]}) using /{scale}")
            return scaled_down

        scaled_up = (int(x * scale), int(y * scale))
        if 0 <= scaled_up[0] < width and 0 <= scaled_up[1] < height:
            print(f"[executor] Adjusted point ({x},{y}) -> ({scaled_up[0]},{scaled_up[1]}) using *{scale}")
            return scaled_up

    clamped_x = min(max(x, 0), max(width - 1, 0))
    clamped_y = min(max(y, 0), max(height - 1, 0))
    if (clamped_x, clamped_y) != (x, y):
        print(f"[executor] Clamped off-screen point ({x},{y}) -> ({clamped_x},{clamped_y})")

    return clamped_x, clamped_y


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
                x, y = _resolve_cursor_point(int(el["x"]), int(el["y"]))
                pyautogui.click(x, y)

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
                    x, y = _resolve_cursor_point(int(el["x"]), int(el["y"]))
                    pyautogui.click(x, y)
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
                x, y = _resolve_cursor_point(int(el["x"]), int(el["y"]))
                pyautogui.scroll(amount, x=x, y=y)

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
            element = elements[el_id]
            if (
                str(element.get("type", "")).lower() == "cdp"
                and int(element.get("x", 0)) == 0
                and int(element.get("y", 0)) == 0
            ):
                print(f"[executor] Warning: element ID {el_id} has no actionable coordinates")
                return None

            return element
        print(f"[executor] Warning: element ID {el_id} not in current snapshot")
        return None
    except (IndexError, ValueError):
        print(f"[executor] Warning: invalid element ID in action: {parts}")
        return None
