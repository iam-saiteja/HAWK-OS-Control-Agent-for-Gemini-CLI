# HAWK — OS Control Agent
### Project Document for Builders

---

## The Problem

Every current approach to AI controlling a computer uses a **vision model** — it takes a screenshot, sends it to a large model (GPT-4V, Claude Vision, etc.), and waits for it to figure out what's on screen. This is:

- **Slow** — 2–5 seconds per action just for perception
- **Expensive** — you're burning tokens on pixels, not reasoning
- **Heavy** — requires GPU or expensive API calls on every loop
- **Not scalable** — can't swap AI brains easily, tightly coupled

The root cause: people are using a sledgehammer (vision model) where a scalpel (structured data extraction) will do.

---

## The Insight

The screen is already structured data. Windows knows exactly where every button, textbox, and label is. You don't need a model to "see" the screen — you just need to ask Windows what's on it.

**The separation:**
- **Perception** → lightweight, deterministic, near-zero compute
- **Reasoning** → Gemini API (persistent chat session)

These two are completely decoupled. The perception layer produces a clean numbered list. The reasoning layer reads it and says what to do next.

---

## What We're Building

**HAWK** — a Windows OS control agent that:

1. Reads the screen as structured text (not pixels) using a 3-method fallback chain
2. Feeds a compact snapshot/diff to Gemini via the API (with conversation memory)
3. Validates and executes Gemini's action (click, type, key, scroll)
4. Self-checks for progress every 5 turns and replans if stuck
5. Repeats until task is done or max turns reached

**V1 scope:** Windows only + Gemini API only.  
**Design goal:** Pluggable — swapping Gemini for another model requires changing one function.

---

## Architecture — Four Layers

```
┌─────────────────────────────────────────┐
│        LAYER 1: PERCEPTION (hawk.py)    │
│                                         │
│  uiautomation  →  CDP  →  WinRT OCR    │
│  (Win32/WPF)    (Electron) (fallback)   │
│  + DPI normalization                    │
└──────────────────┬──────────────────────┘
                   │ raw elements list
┌──────────────────▼──────────────────────┐
│        LAYER 2: BRIDGE (bridge.py)      │
│                                         │
│  Region-bucketed diff engine            │
│  Token budget enforcer                  │
│  Element ID registry                    │
└──────────────────┬──────────────────────┘
                   │ ~50–400 tokens
┌──────────────────▼──────────────────────┐
│        LAYER 3: AGENT (agent.py)        │
│                                         │
│  Gemini API — persistent chat session   │
│  Action history tracking                │
│  Progress verifier every 5 turns        │
└──────────────────┬──────────────────────┘
                   │ validated action string
┌──────────────────▼──────────────────────┐
│        LAYER 4: EXECUTOR (executor.py)  │
│                                         │
│  pyautogui (mouse + keyboard)           │
│  pyperclip (clipboard paste for typing) │
│  Action validation before firing        │
└─────────────────────────────────────────┘
                   │ loop back
                   ▼
             action on screen
```

---

## Layer 1 — Perception (`hawk.py`)

Three methods tried in order. Stop at the first one that returns more than 3 interactive elements.

### DPI Normalization (apply to all methods)

```python
import ctypes

def get_dpi_scale() -> float:
    try:
        return ctypes.windll.shcore.GetScaleFactorForDevice(0) / 100
    except:
        return 1.0
```

Always divide raw pixel coordinates by `dpi_scale` before storing them.

### Method A — `uiautomation` (primary)
**Covers:** Win32, WPF, WinForms, UWP, Qt, MFC  
**Speed:** ~0ms  
**Install:** `pip install uiautomation`

```python
import uiautomation as auto

def get_uiautomation_elements():
    dpi = get_dpi_scale()
    win = auto.GetForegroundControl()
    window_title = win.Name
    elements = []

    def walk(ctrl, depth=0):
        if depth > 6:
            return
        try:
            name = ctrl.Name
            ctype = ctrl.ControlTypeName
            rect = ctrl.BoundingRectangle
            if name and rect.width() > 0:
                elements.append({
                    "name": name,
                    "type": ctype,
                    "x": int((rect.left + rect.width() // 2) / dpi),
                    "y": int((rect.top + rect.height() // 2) / dpi),
                })
        except:
            pass
        for child in ctrl.GetChildren():
            walk(child, depth + 1)

    walk(win)
    return window_title, elements
```

> **Note:** Must run terminal as Administrator for `uiautomation` to work.

### Method B — CDP WebSocket (fallback 1)
**Covers:** Chrome, Electron apps (VS Code, Slack, Discord, Figma, Notion)  
**Speed:** ~10ms  
**Requirement:** Target app launched with `--remote-debugging-port=9222`

```python
import asyncio, json, urllib.request
import websockets

async def _get_cdp_tree_async(port=9222):
    targets = json.loads(urllib.request.urlopen(
        f"http://localhost:{port}/json"
    ).read())
    ws_url = targets[0]["webSocketDebuggerUrl"]
    async with websockets.connect(ws_url) as ws:
        await ws.send(json.dumps({"id": 1, "method": "Accessibility.enable"}))
        await ws.recv()
        await ws.send(json.dumps({"id": 2, "method": "Accessibility.getFullAXTree"}))
        result = json.loads(await ws.recv())
        return result["result"]["nodes"]

def get_cdp_elements(port=9222):
    try:
        nodes = asyncio.run(_get_cdp_tree_async(port))
        elements = []
        for node in nodes:
            name = node.get("name", {}).get("value", "")
            role = node.get("role", {}).get("value", "")
            if name and role not in ("none", "generic", ""):
                elements.append({"name": name, "type": role, "x": 0, "y": 0})
        return elements
    except:
        return []
```

### Method C — WinRT OCR (fallback 2)
**Covers:** Games, custom-rendered UIs, anything that blocks UIA/CDP  
**Speed:** ~80ms  
**Install:** `pip install screen-ocr[winrt] mss`

```python
import screen_ocr, mss

def get_ocr_elements():
    try:
        reader = screen_ocr.Reader.create_quality_reader(backend="winrt")
        with mss.mss() as sct:
            screenshot = sct.grab(sct.monitors[0])
        result = reader.read_image(screenshot)
        elements = []
        for line in result.result.lines:
            for w in line.words:
                elements.append({
                    "name": w.text,
                    "type": "text",
                    "x": int(w.left + w.width / 2),
                    "y": int(w.top + w.height / 2),
                })
        return elements
    except:
        return []
```

### Orchestrator

```python
def get_screen_state() -> tuple[str, list]:
    window_title, elements = get_uiautomation_elements()
    if len(elements) > 3:
        return window_title, elements

    cdp_elements = get_cdp_elements()
    if len(cdp_elements) > 3:
        return window_title, cdp_elements

    return window_title, get_ocr_elements()
```

---

## Layer 2 — Bridge (`bridge.py`)

Converts raw elements into a compact numbered format. Uses region-bucketed hashing for stable diffs (resilient to window resizes and slight coordinate shifts).

### Output format (Turn 1 — full snapshot)

```
WINDOW: Visual Studio Code
[1] btn "File" (30, 20)
[2] btn "Edit" (70, 20)
[3] tab "hawk.py" (200, 45)
[4] input "" (680, 400)
[5] btn "Run" (1200, 20)
```

### Diff format (Turn 2+)

```
DIFF:
+ [6] dialog "Save As?" (600, 300)
+ [7] btn "Save" (650, 380)
+ [8] btn "Cancel" (730, 380)
- [5] btn "Run" removed
```

### Region-bucketed hashing

Instead of exact `(name, x, y)` comparison, elements are hashed by `(name, type, x_bucket, y_bucket)` where each bucket is a 100px grid cell. This prevents false-positive diffs on window resize.

```python
def _element_key(self, el: dict) -> tuple:
    return (
        el["name"],
        el["type"],
        el["x"] // 100,   # 100px grid bucket
        el["y"] // 100,
    )
```

### `bridge.py` — complete implementation

```python
class Bridge:
    def __init__(self):
        self.prev_snapshot: dict = {}

    def format_snapshot(self, elements: list, window_title: str) -> str:
        current = {}
        lines = [f"WINDOW: {window_title}"]
        for i, el in enumerate(elements, 1):
            etype = self._classify(el["type"])
            lines.append(f'[{i}] {etype} "{el["name"]}" ({el["x"]},{el["y"]})')
            current[i] = el
        self.prev_snapshot = current
        return "\n".join(lines)

    def format_diff(self, elements: list, window_title: str) -> str:
        current = {}
        for i, el in enumerate(elements, 1):
            current[i] = el

        prev_keys = {self._element_key(v) for v in self.prev_snapshot.values()}
        curr_keys = {self._element_key(v) for v in current.values()}

        added = curr_keys - prev_keys
        removed = prev_keys - curr_keys

        if not added and not removed:
            self.prev_snapshot = current
            return "DIFF: no changes"

        lines = [f"WINDOW: {window_title}", "DIFF:"]
        next_id = max(self.prev_snapshot.keys(), default=0)

        for el in elements:
            if self._element_key(el) in added:
                next_id += 1
                etype = self._classify(el["type"])
                lines.append(f'+ [{next_id}] {etype} "{el["name"]}" ({el["x"]},{el["y"]})')
                current[next_id] = el

        for key in removed:
            for i, v in self.prev_snapshot.items():
                if self._element_key(v) == key:
                    lines.append(f'- [{i}] "{v["name"]}" removed')

        self.prev_snapshot = current
        return "\n".join(lines)

    def get_elements(self) -> dict:
        return self.prev_snapshot

    def _element_key(self, el: dict) -> tuple:
        return (el["name"], el["type"], el["x"] // 100, el["y"] // 100)

    def _classify(self, control_type: str) -> str:
        mapping = {
            "ButtonControl": "btn",
            "EditControl": "input",
            "TextControl": "text",
            "MenuItemControl": "menu",
            "TabItemControl": "tab",
            "CheckBoxControl": "check",
            "ComboBoxControl": "select",
            "button": "btn",
            "textbox": "input",
            "link": "link",
            "menuitem": "menu",
        }
        return mapping.get(control_type, "el")
```

---

## Layer 3 — Agent (`agent.py`)

Calls the Gemini API with a persistent chat session so the model remembers previous actions across turns. Includes a progress verifier every 5 turns to detect if the agent is stuck.

### Setup

```
pip install google-generativeai
```

Set your API key as an environment variable:
```
GEMINI_API_KEY=your_key_here
```

### System prompt

```
You control a Windows computer. Each turn you receive the current screen state.

Respond with EXACTLY ONE action on a single line:
  click <id>
  type <id> <text>
  key <combo>       (examples: ctrl+s, alt+f4, enter, tab, win)
  scroll <id> <up|down>
  done

Nothing else. No explanation. One line only.
```

### `agent.py` — complete implementation

```python
import os
import google.generativeai as genai
from typing import Optional

SYSTEM_PROMPT = """You control a Windows computer. Each turn you receive the current screen state.

Respond with EXACTLY ONE action on a single line:
  click <id>
  type <id> <text>
  key <combo>
  scroll <id> <up|down>
  done

Nothing else. No explanation. One line only."""

VALID_COMMANDS = ("click", "type", "key", "scroll", "done")

genai.configure(api_key=os.environ["GEMINI_API_KEY"])
_model = genai.GenerativeModel("gemini-2.0-flash", system_instruction=SYSTEM_PROMPT)
_chat = _model.start_chat(history=[])


def ask_agent(snapshot: str, task: str) -> str:
    """Send screen snapshot to Gemini and return one action string."""
    message = f"Task: {task}\n\nScreen:\n{snapshot}"
    try:
        response = _chat.send_message(message)
        reply = response.text.strip()
        for line in reply.splitlines():
            line = line.strip()
            if line and line.split()[0] in VALID_COMMANDS:
                return line
        return "done"
    except Exception as e:
        print(f"[agent] Gemini error: {e}")
        return "done"


def verify_progress(task: str, action_history: list[str], snapshot: str) -> str:
    """
    Called every 5 turns to check if the agent is on track.
    Returns: 'CONTINUE', 'REPLAN', or 'DONE'
    """
    history_str = "\n".join(f"- {a}" for a in action_history[-10:])
    message = f"""Task: {task}

Actions taken so far:
{history_str}

Current screen:
{snapshot}

Is the task complete, still in progress, or is the agent stuck/going wrong?
Reply with exactly one word: CONTINUE, REPLAN, or DONE"""
    try:
        response = _chat.send_message(message)
        reply = response.text.strip().upper()
        for word in ("DONE", "REPLAN", "CONTINUE"):
            if word in reply:
                return word
        return "CONTINUE"
    except:
        return "CONTINUE"


def reset_chat():
    """Call this between tasks to clear conversation history."""
    global _chat
    _chat = _model.start_chat(history=[])
```

> **Model choice:** `gemini-2.0-flash` is recommended — it's fast, cheap, and well within free tier limits (1,000 requests/day free). For more complex tasks, swap to `gemini-2.5-pro` (50 req/day free).

---

## Layer 4 — Executor (`executor.py`)

Validates actions before firing, uses clipboard paste for reliable Unicode typing.

### Install

```
pip install pyautogui pyperclip
```

### `executor.py` — complete implementation

```python
import time
import pyautogui
import pyperclip

pyautogui.FAILSAFE = True   # move mouse to top-left corner to abort


def execute_action(action: str, elements: dict) -> bool:
    """
    Execute one action. Returns True to continue loop, False to stop.
    elements: dict of {id: {"x": int, "y": int, ...}}
    """
    parts = action.strip().split()
    if not parts:
        return True

    cmd = parts[0]

    try:
        if cmd == "click":
            el = _get_element(parts, elements)
            if el:
                pyautogui.click(el["x"], el["y"])

        elif cmd == "type":
            el = _get_element(parts, elements)
            if el and len(parts) >= 3:
                text = " ".join(parts[2:])
                pyautogui.click(el["x"], el["y"])
                time.sleep(0.15)
                pyperclip.copy(text)
                pyautogui.hotkey("ctrl", "v")   # paste — handles Unicode, spaces, special chars

        elif cmd == "key":
            if len(parts) >= 2:
                keys = parts[1].split("+")
                pyautogui.hotkey(*keys)

        elif cmd == "scroll":
            el = _get_element(parts, elements)
            if el and len(parts) >= 3:
                direction = parts[2]
                amount = -3 if direction == "down" else 3
                pyautogui.scroll(amount, x=el["x"], y=el["y"])

        elif cmd == "done":
            return False

    except Exception as e:
        print(f"[executor] Error executing '{action}': {e}")

    time.sleep(0.1)
    return True


def _get_element(parts: list, elements: dict) -> dict | None:
    """Safely look up element by ID. Logs warning if not found."""
    try:
        el_id = int(parts[1])
        if el_id in elements:
            return elements[el_id]
        print(f"[executor] Warning: element ID {el_id} not in current snapshot, skipping")
        return None
    except (IndexError, ValueError):
        print(f"[executor] Warning: could not parse element ID from '{parts}'")
        return None
```

---

## Main Loop (`main.py`)

```python
import sys
import time
from hawk import get_screen_state
from bridge import Bridge
from agent import ask_agent, verify_progress, reset_chat
from executor import execute_action

MAX_TURNS = 25
VERIFY_EVERY = 5


def run(task: str):
    bridge = Bridge()
    action_history = []
    turn = 0

    reset_chat()
    print(f"[hawk] Task: {task}")
    print("[hawk] Focusing target window in 3 seconds...")
    time.sleep(3)

    while turn < MAX_TURNS:
        window_title, elements = get_screen_state()

        if not elements:
            print("[hawk] No elements found, retrying...")
            time.sleep(1)
            continue

        if turn == 0:
            snapshot = bridge.format_snapshot(elements, window_title)
        else:
            snapshot = bridge.format_diff(elements, window_title)

        # Progress check every VERIFY_EVERY turns
        if turn > 0 and turn % VERIFY_EVERY == 0:
            status = verify_progress(task, action_history, snapshot)
            print(f"[hawk] Verifier says: {status}")
            if status == "DONE":
                print("[hawk] Task complete (verified).")
                break
            elif status == "REPLAN":
                print("[hawk] Replanning — sending full snapshot to reset context.")
                snapshot = bridge.format_snapshot(elements, window_title)

        print(f"\n--- Turn {turn} | {window_title} ---")
        print(snapshot[:400])

        action = ask_agent(snapshot, task)
        print(f"[hawk] Action: {action}")
        action_history.append(action)

        current_elements = bridge.get_elements()
        should_continue = execute_action(action, current_elements)

        if not should_continue:
            print("[hawk] Task complete.")
            break

        turn += 1
        time.sleep(0.8)

    if turn >= MAX_TURNS:
        print(f"[hawk] Reached max turns ({MAX_TURNS}). Stopping.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('Usage: python main.py "your task here"')
        sys.exit(1)
    run(" ".join(sys.argv[1:]))
```

---

## File Structure

```
hawk/
├── main.py              # entry point, main loop
├── hawk.py              # perception layer (3-method fallback)
├── bridge.py            # snapshot formatter + region-bucketed diff
├── agent.py             # Gemini API caller + progress verifier
├── executor.py          # action validator + input executor
├── requirements.txt
└── tests/
    ├── test_hawk.py
    ├── test_bridge.py
    └── test_executor.py
```

**requirements.txt**
```
uiautomation
screen-ocr[winrt]
mss
websockets
pyautogui
pyperclip
google-generativeai
pytest
```

---

## Environment Setup

```bash
# 1. Create and activate venv (run terminal as Administrator)
python -m venv venv
venv\Scripts\activate

# 2. Install dependencies
pip install uiautomation screen-ocr[winrt] mss websockets pyautogui pyperclip google-generativeai pytest

# 3. Set API key (add this to your system environment variables permanently)
set GEMINI_API_KEY=your_key_here
```

Get your free API key at: https://aistudio.google.com/app/apikey

---

## How to Test

### Step 1 — Test perception
Open Notepad, click inside it, then run:
```python
from hawk import get_screen_state
title, els = get_screen_state()
print(title)
for e in els[:10]:
    print(e)
```
Expected: you see elements like `{"name": "Text Editor", "type": "EditControl", "x": 400, "y": 300}`.

### Step 2 — Test bridge
```python
from bridge import Bridge
b = Bridge()
els = [
    {"name": "File", "type": "ButtonControl", "x": 30, "y": 20},
    {"name": "Save", "type": "ButtonControl", "x": 100, "y": 400},
]
print(b.format_snapshot(els, "Notepad"))
```
Expected:
```
WINDOW: Notepad
[1] btn "File" (30,20)
[2] btn "Save" (100,400)
```

### Step 3 — Test executor alone
```python
from executor import execute_action
fake = {1: {"x": 960, "y": 540, "name": "test", "type": "btn"}}
execute_action("click 1", fake)
# Mouse should click center of screen
```

### Step 4 — Test Gemini API connection
```python
from agent import ask_agent
snapshot = 'WINDOW: Notepad\n[1] input "Text Editor" (400,300)'
print(ask_agent(snapshot, "type hello world in the editor"))
# Should return something like: type 1 hello world
```

### Step 5 — End to end
```bash
python main.py "open notepad and type hello world"
```

---

## Known Limitations and Fixes

| Problem | Cause | Fix |
|---|---|---|
| uiautomation returns nothing | Not running as Administrator | Always open terminal with Run as Administrator |
| uiautomation returns nothing | App uses DirectUI/custom renderer | Falls through to CDP or OCR automatically |
| CDP connection refused | App not launched with debug port | Add `--remote-debugging-port=9222` to app launch args |
| Mouse clicks wrong spot | HiDPI display scaling | Already handled in `hawk.py` via `get_dpi_scale()` |
| Gemini returns multi-line | Model goes off-format occasionally | Already handled in `ask_agent()` — scans line-by-line |
| Typing skips characters | pyautogui typewrite issue | Fixed — uses clipboard paste via pyperclip instead |
| Element ID missing | Diff updated IDs between turns | Already handled in `executor.py` via `_get_element()` validation |

---

## Pluggable Brain

To swap Gemini for another model, only `agent.py` needs to change. Everything else — hawk.py, bridge.py, executor.py, main.py — stays identical.

```python
# Example: swap to Claude API
def ask_agent(snapshot: str, task: str) -> str:
    # replace with anthropic SDK call
    pass
```

---

## Free Tier API Limits (Gemini)

| Model | Free Requests/Day | Recommended For |
|---|---|---|
| gemini-2.0-flash | 1,500 | Default — development + daily use |
| gemini-2.5-flash-lite | 1,000 | Lightweight tasks |
| gemini-2.5-pro | 50 | Complex multi-step tasks only |

At 5–20 API calls per task run, `gemini-2.0-flash` gives you **75–300 task runs per day free**.

---

## Build Order

1. `hawk.py` — prove perception works on Notepad first. Print element trees.
2. `bridge.py` — take those elements, produce clean numbered output. Verify token count stays under 500.
3. `agent.py` — test with hardcoded snapshots. Confirm Gemini returns valid one-line actions.
4. `executor.py` — test each action type (click, type, key, scroll) in isolation.
5. `main.py` — connect the loop. Test with "click the File menu".
6. Add CDP path for Electron apps.
7. Add WinRT OCR fallback last.

**Prove each layer works before connecting the next.**

---

## V1 Success Criteria

- [ ] Can open Notepad and type text
- [ ] Can navigate a browser (click links, fill forms)
- [ ] Can open VS Code and create a new file
- [ ] Perception takes under 200ms per turn
- [ ] Token usage under 500 per turn
- [ ] Swapping Gemini for another API takes under 5 minutes
- [ ] Progress verifier correctly detects task completion
