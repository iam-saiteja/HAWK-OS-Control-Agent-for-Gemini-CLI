# HAWK — OS Control Agent for Gemini CLI
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
- **Reasoning** → Gemini CLI (or any brain)

These two should be completely decoupled. The perception layer produces a clean numbered list. The reasoning layer reads it and says what to do next. That's it.

---

## What We're Building

**HAWK** — a Gemini CLI extension that controls Windows by:

1. Reading the screen as structured text (not pixels)
2. Feeding that to Gemini CLI in a compact format
3. Executing Gemini's action (click, type, key)
4. Repeating

**V1 scope:** Windows only + Gemini CLI only.  
**Design goal:** Pluggable — swapping Gemini for Claude Code or any other brain should require changing one line.

---

## Architecture — Three Layers

```
┌─────────────────────────────────────────┐
│           LAYER 1: HAWK (perception)    │
│                                         │
│  uiautomation  →  CDP  →  WinRT OCR    │
│  (Win32/WPF)    (Electron) (fallback)   │
└──────────────────┬──────────────────────┘
                   │ compact snapshot
┌──────────────────▼──────────────────────┐
│           LAYER 2: BRIDGE               │
│                                         │
│   Diff engine + token budget enforcer   │
│   Formats output as numbered list       │
└──────────────────┬──────────────────────┘
                   │ ~50–400 tokens
┌──────────────────▼──────────────────────┐
│     LAYER 3: GEMINI CLI + EXECUTOR      │
│                                         │
│   Gemini reasons → one action output    │
│   Executor fires Win32 input event      │
└─────────────────────────────────────────┘
                   │ loop back
                   ▼
             action on screen
```

---

## Layer 1 — Perception (HAWK)

Three methods tried in order. Stop at the first one that returns enough elements (threshold: more than 3 interactive elements found).

### Method A — `uiautomation` (primary)
**Covers:** Win32, WPF, WinForms, UWP, Qt, MFC  
**Speed:** ~0ms  
**Install:** `pip install uiautomation`

```python
import uiautomation as auto

def get_active_window_tree():
    win = auto.GetForegroundControl()
    elements = []
    
    def walk(ctrl, depth=0):
        if depth > 6:  # don't go too deep
            return
        try:
            name = ctrl.Name
            ctype = ctrl.ControlTypeName
            rect = ctrl.BoundingRectangle
            if name and rect.width() > 0:
                elements.append({
                    "name": name,
                    "type": ctype,
                    "x": rect.left + rect.width() // 2,
                    "y": rect.top + rect.height() // 2,
                })
        except:
            pass
        for child in ctrl.GetChildren():
            walk(child, depth + 1)
    
    walk(win)
    return elements
```

### Method B — CDP WebSocket (fallback 1)
**Covers:** Chrome, Electron apps (VS Code, Slack, Discord, Figma, Notion)  
**Speed:** ~10ms  
**Requirement:** Target app launched with `--remote-debugging-port=9222`

```python
import asyncio, json
import websockets

async def get_cdp_tree(port=9222):
    # Get list of targets
    import urllib.request
    targets = json.loads(urllib.request.urlopen(
        f"http://localhost:{port}/json"
    ).read())
    
    ws_url = targets[0]["webSocketDebuggerUrl"]
    
    async with websockets.connect(ws_url) as ws:
        # Enable accessibility
        await ws.send(json.dumps({
            "id": 1, "method": "Accessibility.enable"
        }))
        await ws.recv()
        
        # Get full AX tree
        await ws.send(json.dumps({
            "id": 2, "method": "Accessibility.getFullAXTree"
        }))
        result = json.loads(await ws.recv())
        return result["result"]["nodes"]
```

For Electron apps you don't control (e.g. VS Code already running), use:  
`code --remote-debugging-port=9222` or set it in the app's launch shortcut.

### Method C — WinRT OCR (fallback 2)
**Covers:** Games, custom-rendered UIs, anything else  
**Speed:** ~80ms  
**Install:** `pip install screen-ocr[winrt]`

```python
import screen_ocr
import mss

def get_screen_text_with_coords():
    reader = screen_ocr.Reader.create_quality_reader(backend="winrt")
    
    with mss.mss() as sct:
        screenshot = sct.grab(sct.monitors[0])
    
    result = reader.read_image(screenshot)
    elements = []
    for word in result.result.lines:
        for w in word.words:
            elements.append({
                "name": w.text,
                "type": "text",
                "x": int(w.left + w.width / 2),
                "y": int(w.top + w.height / 2),
            })
    return elements
```

---

## Layer 2 — Bridge

Converts raw element lists into a compact numbered format, and only sends diffs after turn 1.

### Output format (what Gemini sees)

```
WINDOW: Visual Studio Code
[1] btn "File" (30, 20)
[2] btn "Edit" (70, 20)
[3] tab "hawk.py" (200, 45) [active]
[4] editor "" (680, 400)
[5] btn "Run" (1200, 20)
```

That's it. No XML, no JSON, no raw HTML. Every interactive element gets a number and a coordinate.

### Diff format (turns 2+)

```
DIFF:
+ [6] dialog "Save As?" (600, 300)
+ [7] btn "Save" (650, 380)
+ [8] btn "Cancel" (730, 380)
- [5] btn "Run" removed
```

This keeps token usage to 50–150 tokens per turn after the first.

### bridge.py

```python
class Bridge:
    def __init__(self):
        self.prev_elements = {}
    
    def format_snapshot(self, elements, window_title):
        current = {}
        lines = [f"WINDOW: {window_title}"]
        
        for i, el in enumerate(elements, 1):
            etype = self._classify(el["type"])
            label = f'[{i}] {etype} "{el["name"]}" ({el["x"]},{el["y"]})'
            lines.append(label)
            current[i] = el
        
        self.prev_elements = current
        return "\n".join(lines)
    
    def format_diff(self, elements, window_title):
        # Compare to previous, emit only changes
        # (implement set diff on element names+coords)
        pass
    
    def _classify(self, control_type):
        mapping = {
            "ButtonControl": "btn",
            "EditControl": "input",
            "TextControl": "text",
            "MenuItemControl": "menu",
            "TabItemControl": "tab",
            "CheckBoxControl": "check",
            "ComboBoxControl": "select",
        }
        return mapping.get(control_type, "el")
```

---

## Layer 3 — Gemini CLI Extension + Executor

### System prompt (same for every brain)

```
You control a Windows computer. Each turn you receive the current screen state.

Respond with EXACTLY ONE action on a single line:
  click <id>
  type <id> <text>
  key <combo>       (examples: ctrl+s, alt+f4, enter, tab)
  scroll <id> <up|down>
  done

Nothing else. No explanation. One line only.
```

### gemini_ext.py

```python
import subprocess, re
import pyautogui  # pip install pyautogui

def ask_gemini(snapshot: str, task: str) -> str:
    prompt = f"Task: {task}\n\nScreen:\n{snapshot}"
    
    result = subprocess.run(
        ["gemini", "-p", prompt],
        capture_output=True, text=True
    )
    return result.stdout.strip()

def execute_action(action: str, elements: dict):
    parts = action.strip().split()
    cmd = parts[0]
    
    if cmd == "click" and len(parts) >= 2:
        el_id = int(parts[1])
        el = elements[el_id]
        pyautogui.click(el["x"], el["y"])
    
    elif cmd == "type" and len(parts) >= 3:
        el_id = int(parts[1])
        text = " ".join(parts[2:])
        el = elements[el_id]
        pyautogui.click(el["x"], el["y"])
        pyautogui.typewrite(text, interval=0.05)
    
    elif cmd == "key" and len(parts) >= 2:
        combo = parts[1]
        keys = combo.split("+")
        pyautogui.hotkey(*keys)
    
    elif cmd == "scroll" and len(parts) >= 3:
        el_id = int(parts[1])
        direction = parts[2]
        el = elements[el_id]
        amount = 3 if direction == "down" else -3
        pyautogui.scroll(amount, x=el["x"], y=el["y"])
    
    elif cmd == "done":
        return False  # signal loop to stop
    
    return True  # continue loop
```

### Main loop

```python
# main.py
from hawk import get_screen_state
from bridge import Bridge
from gemini_ext import ask_gemini, execute_action

def run(task: str):
    bridge = Bridge()
    turn = 0
    
    while turn < 20:  # max 20 actions
        window_title, elements = get_screen_state()
        
        if turn == 0:
            snapshot = bridge.format_snapshot(elements, window_title)
        else:
            snapshot = bridge.format_diff(elements, window_title)
        
        action = ask_gemini(snapshot, task)
        print(f"[{turn}] {action}")
        
        should_continue = execute_action(action, elements)
        if not should_continue:
            print("Task complete.")
            break
        
        turn += 1
        import time; time.sleep(0.5)  # let UI settle

if __name__ == "__main__":
    import sys
    task = " ".join(sys.argv[1:])
    run(task)
```

---

## File Structure

```
hawk/
├── main.py              # entry point, main loop
├── hawk.py              # perception layer (all 3 methods)
├── bridge.py            # snapshot formatter + diff engine
├── gemini_ext.py        # gemini CLI caller + action executor
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
pyautogui
mss
websockets
```

---

## How to Test

### Step 1 — Test perception in isolation
Open Notepad. Run:
```python
from hawk import get_screen_state
title, els = get_screen_state()
for e in els:
    print(e)
```
Expected: you should see elements like `{"name": "Text Editor", "type": "EditControl", "x": 400, "y": 300}`.  
If you get nothing → the active window is not in focus. Fix: click Notepad first, then run.

### Step 2 — Test bridge output
```python
from bridge import Bridge
b = Bridge()
fake_elements = [
    {"name": "File", "type": "MenuBarControl", "x": 30, "y": 20},
    {"name": "Save", "type": "ButtonControl", "x": 100, "y": 400},
]
print(b.format_snapshot(fake_elements, "Notepad"))
```
Expected output:
```
WINDOW: Notepad
[1] el "File" (30,20)
[2] btn "Save" (100,400)
```

### Step 3 — Test action executor
```python
from gemini_ext import execute_action
fake_elements = {1: {"x": 400, "y": 300}}
execute_action("click 1", fake_elements)
# your mouse should move and click at (400, 300)
```

### Step 4 — Test CDP (for Electron apps)
Open VS Code with: `code --remote-debugging-port=9222`  
Then run:
```python
import asyncio
from hawk import get_cdp_tree
nodes = asyncio.run(get_cdp_tree())
print(len(nodes), "nodes found")
```
Expected: 50+ nodes.

### Step 5 — End to end test
```bash
python main.py "open notepad and type hello world"
```
Watch your screen. Gemini should click Start, search for Notepad, open it, click the editor, and type.

---

## Known Limitations + How to Handle Them

| Problem | Cause | Fix |
|---|---|---|
| UIAutomation returns 0 elements | App uses DirectUI / custom rendering | Fall through to CDP or WinRT OCR |
| CDP connection refused | App not launched with debug port | Add `--remote-debugging-port=9222` to launch args |
| WinRT OCR misses buttons (no text) | Icon-only buttons | Accept this — send coordinates of center area, let Gemini infer |
| Gemini returns garbage | Bad prompt or noisy snapshot | Filter elements: skip invisible, zero-size, and duplicate-name nodes |
| Mouse click lands wrong | HiDPI / display scaling | Get DPI scale factor and divide coordinates: `x = x / dpi_scale` |

### HiDPI fix
```python
import ctypes
dpi_scale = ctypes.windll.shcore.GetScaleFactorForDevice(0) / 100
```

---

## What "Pluggable Brain" Means in Practice

To swap Gemini CLI for Claude Code, you only change `ask_gemini`:

```python
# For Claude Code
def ask_brain(snapshot: str, task: str) -> str:
    prompt = f"Task: {task}\n\nScreen:\n{snapshot}"
    result = subprocess.run(
        ["claude", "-p", prompt],
        capture_output=True, text=True
    )
    return result.stdout.strip()
```

The system prompt, the snapshot format, the action format, the executor — none of it changes. That's the whole point.

---

## Build Order (Recommended)

1. `hawk.py` — get `uiautomation` working on your machine first. Print element trees of Notepad and Chrome.
2. `bridge.py` — take those elements, produce clean numbered output. Verify token count stays under 500.
3. `gemini_ext.py` — wire Gemini CLI. Test with hardcoded snapshots first (don't loop yet).
4. `main.py` — connect the loop. Test with simple tasks: "click the File menu", "type hello in notepad".
5. Add CDP path for Electron apps.
6. Add WinRT OCR fallback last.

**Don't build everything at once. Prove each layer works before connecting the next.**

---

## Success Criteria for V1

- [ ] Can open Notepad and type text
- [ ] Can navigate a browser (click links, fill forms)
- [ ] Can open VS Code and create a new file
- [ ] Perception takes under 200ms per turn
- [ ] Token usage under 500 per turn
- [ ] Swapping Gemini → Claude Code takes under 5 minutes
