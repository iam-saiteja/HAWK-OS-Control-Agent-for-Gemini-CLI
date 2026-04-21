# Copilot Working Instructions for HAWK

## Objective
Build and maintain HAWK as a Windows-first OS control agent using structured perception (UIA/CDP/OCR) and a pluggable reasoning brain powered by the Gemini API.

## Non-Negotiable Design Rules
1. Keep perception and reasoning fully decoupled — `hawk.py` never calls `agent.py`.
2. Preserve the compact numbered snapshot/diff format exactly as specified.
3. Prefer deterministic extraction over vision models for perception.
4. Keep the reasoning interface single-action-per-turn — one line, no explanation.
5. Maintain pluggability: swapping the AI brain means only modifying `agent.py`.
6. Always validate element IDs in `executor.py` before firing any input event.
7. Use clipboard paste (`pyperclip`) for all text typing — never `pyautogui.typewrite()`.

## Architecture — Four Files

| File | Responsibility |
|---|---|
| `hawk.py` | Perception only — UIA → CDP → WinRT OCR fallback chain |
| `bridge.py` | Format snapshot / diff, region-bucketed element hashing |
| `agent.py` | Gemini API chat session, action parsing, progress verifier |
| `executor.py` | Validate and execute click/type/key/scroll/done |
| `main.py` | Loop: perceive → format → reason → verify (every 5 turns) → execute |

## Current V1 Scope
- Platform: Windows
- Brain: Gemini API (`gemini-2.0-flash` default)
- Chat: Persistent session across turns (model retains action history)
- Loop: perceive → format → reason → execute → repeat (max 25 turns)
- Verifier: Every 5 turns, ask Gemini if task is DONE / CONTINUE / REPLAN

## Output Contract (Reasoning Layer)
`agent.py` must always return exactly one of:
```
click <id>
type <id> <text>
key <combo>
scroll <id> <up|down>
done
```
No extra text. If Gemini returns multiple lines, scan line-by-line and take the first valid command. Default to `done` if nothing valid is found.

## Gemini API Setup
- Library: `google-generativeai`
- Model: `gemini-2.0-flash` (free tier: 1,500 req/day)
- Auth: `GEMINI_API_KEY` environment variable — never hardcode the key
- Session: One persistent `chat = model.start_chat(history=[])` per task run
- Reset: Call `reset_chat()` between tasks to clear history

## Coding Priorities
1. Robust fallbacks: UIA → CDP → OCR — never let perception silently fail
2. DPI normalization on all coordinates — use `ctypes.windll.shcore.GetScaleFactorForDevice(0) / 100`
3. Low latency per turn (<200ms target for perception)
4. Token efficiency (<500 tokens/turn including diff)
5. Defensive error handling — OS integration code must not raise uncaught exceptions
6. Safe defaults when external tools are unavailable (return empty list, not crash)

## Diff Stability Rule
Never compare elements by exact `(name, x, y)` — this breaks on window resize.
Always hash elements by `(name, type, x // 100, y // 100)` (100px grid buckets).

## Test Strategy
- Unit test `bridge.py` formatting and diffs with hardcoded element lists.
- Unit test `executor.py` action routing with a mock element dict.
- Unit test `agent.py` action parsing (give it multi-line Gemini output, confirm one line returned).
- Keep OS integration thin — `hawk.py` functions should be callable independently.
- All tests must run without a real screen (use fake elements / mock where needed).

## Public Interface — Do Not Change Signatures

```python
# hawk.py
def get_screen_state() -> tuple[str, list]: ...

# bridge.py
class Bridge:
    def format_snapshot(self, elements: list, window_title: str) -> str: ...
    def format_diff(self, elements: list, window_title: str) -> str: ...
    def get_elements(self) -> dict: ...

# agent.py
def ask_agent(snapshot: str, task: str) -> str: ...
def verify_progress(task: str, action_history: list[str], snapshot: str) -> str: ...
def reset_chat() -> None: ...

# executor.py
def execute_action(action: str, elements: dict) -> bool: ...
```

## Editing Guidelines
- Do not rewrite architecture unless explicitly requested.
- Do not rename `agent.py` back to `gemini_ext.py` — the new name reflects that the brain is swappable.
- Add docstrings and type hints on all new public functions.
- Update `requirements.txt` when adding any new dependency.
- Prefer small, isolated changes — one concern per commit.
