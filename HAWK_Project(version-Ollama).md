# HAWK — OS Control Agent
### Project Document for Builders (Version: Ollama)

---

## The Problem

Most desktop-control agents depend on screenshot-first vision reasoning. That approach is:

- Slow per action loop
- Token-heavy and expensive when remote APIs are used
- Hard to iterate safely because perception and reasoning are tightly coupled

The core issue is overusing vision where structured UI data is already available.

---

## The Insight

Windows can expose structured UI elements directly (name, type, coordinates). So we split the system into:

- Perception: deterministic extraction from UIA/CDP/OCR
- Reasoning: local Ollama model that decides the next action

This keeps the architecture pluggable while avoiding external API dependency for reasoning.

---

## What This Version Builds

HAWK controls Windows by running a closed loop:

1. Capture active screen state as structured elements
2. Convert elements to compact snapshot/diff text
3. Ask local Ollama for exactly one next action
4. Validate and execute that action
5. Re-check progress every 5 turns and continue/replan/stop

Version scope:
- Windows-first runtime
- Local model via Ollama Python SDK
- No Gemini API dependency

---

## Architecture (Current)

```
┌─────────────────────────────────────────┐
│      LAYER 1: PERCEPTION (hawk.py)      │
│  UIAutomation → CDP → WinRT OCR         │
└──────────────────┬──────────────────────┘
                   │ structured elements
┌──────────────────▼──────────────────────┐
│       LAYER 2: BRIDGE (bridge.py)       │
│  snapshot formatter + stable diff IDs   │
└──────────────────┬──────────────────────┘
                   │ compact text context
┌──────────────────▼──────────────────────┐
│        LAYER 3: AGENT (agent.py)        │
│  Ollama chat + action extraction        │
│  verifier: CONTINUE / REPLAN / DONE     │
└──────────────────┬──────────────────────┘
                   │ single action string
┌──────────────────▼──────────────────────┐
│      LAYER 4: EXECUTOR (executor.py)    │
│  click/type/key/scroll/launch actions   │
└─────────────────────────────────────────┘
```

---

## Layer 1 — Perception (hawk/hawk.py)

Method order and fallback:
1. UIAutomation tree from active foreground app
2. CDP accessibility tree for debug-port apps
3. WinRT OCR as final fallback

Key behaviors:
- Applies DPI scaling normalization
- Deduplicates repeated elements
- Returns the first source with enough actionable elements

---

## Layer 2 — Bridge (hawk/bridge.py)

Responsibilities:
- Convert raw elements to numbered lines: `[id] type "name" (x,y)`
- Keep stable IDs across turns where possible
- Emit delta lines (`+` added, `-` removed) for efficient context updates
- Use coarse coordinate bucketing to avoid noisy diffs from tiny UI shifts

---

## Layer 3 — Agent (hawk/agent.py)

This version uses Ollama directly:
- Imports `ollama`
- Reads model from `OLLAMA_MODEL` (default `qwen2:7b`)
- Maintains `_chat_history` across turns
- Calls:
  - `ollama.chat(...)` for next-action reasoning
  - `ollama.generate(...)` for periodic progress verification

Supported action contract:
- `click <id>`
- `type <id> <text>`
- `key <combo>`
- `scroll <id> <up|down>`
- `launch <app_name>`
- `done`

Special notes:
- `launch <app_name>` is a first-class command in this branch
- `type 0 <text>` is supported for blind typing when no elements are available
- Invalid or noisy model output is sanitized by `_extract_action(...)`

---

## Layer 4 — Executor (hawk/executor.py)

Execution engine details:
- Mouse/keyboard automation via `pyautogui`
- Text paste path via `pyperclip` + `ctrl+v` for reliability
- Handles launch flow: Win key → app search text → Enter
- Safely ignores invalid element IDs and keeps loop alive unless `done`

---

## Main Loop (hawk/main.py)

Runtime loop behavior:
- Calls `reset_chat()` at task start
- Waits 3 seconds for target-window focus
- Retries screen extraction when element list is empty
- Falls back to blind-typing snapshot if still empty
- Every 5 turns calls verifier and can force replan via full snapshot
- Stops on `done` or `max_turns`

---

## File Structure (Current)

```
hawk/
├── main.py        # loop orchestration
├── hawk.py        # perception and fallback chain
├── bridge.py      # snapshot/diff formatter
├── agent.py       # Ollama reasoning + verification
├── executor.py    # input execution layer

tests/
├── test_agent.py
├── test_bridge.py
├── test_executor.py
└── test_hawk.py
```

---

## Dependencies (requirements.txt)

- uiautomation
- screen-ocr[winrt]
- mss
- websockets
- pyautogui
- pyperclip
- ollama
- pytest

---

## Environment Setup (Ollama)

1. Create and activate virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Install project dependencies

```powershell
pip install -r requirements.txt
```

3. Install and run Ollama desktop/service locally

```powershell
ollama pull qwen2:7b
```

4. Optional: choose a different model

```powershell
$env:OLLAMA_MODEL = "qwen2:7b"
```

---

## Run and Test

Run the agent:

```powershell
python -m hawk.main "open notepad and type hello world"
```

Run tests:

```powershell
pytest -q
```

---

## Change From Gemini Version

Compared to the Gemini build (`HAWK_project(version-1).md`):

- Reasoning backend replaced from `google-generativeai` to local `ollama`
- API-key setup removed in favor of local model management
- Added `launch <app_name>` action path in the executor contract
- Added blind-typing support path (`type 0 <text>`) when no elements are available

This makes the system fully local for reasoning while preserving the same perception and execution architecture.
