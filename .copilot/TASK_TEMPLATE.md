# Task Template for Copilot

Use this structure when implementing a new feature or change in HAWK.

## Task
<!-- Describe what to build or fix in one paragraph -->

## Constraints
- Windows-first
- Keep perception (`hawk.py`) and reasoning (`agent.py`) fully decoupled
- Keep model output as single-action-per-turn format (no multi-line responses)
- Use Gemini API with persistent chat session — do not use subprocess or CLI
- Use clipboard paste (`pyperclip`) for typing — never `pyautogui.typewrite()`
- Validate element IDs in `executor.py` before firing any input

## Files Expected
- `hawk/hawk.py` — perception (UIA → CDP → WinRT OCR fallback)
- `hawk/bridge.py` — snapshot/diff formatter with region-bucketed hashing
- `hawk/agent.py` — Gemini API chat session + progress verifier
- `hawk/executor.py` — validated input executor
- `hawk/main.py` — main loop with verifier every 5 turns
- `tests/*` — coverage for new logic

## Acceptance Checklist
- [ ] Works in local loop for at least one app (Notepad or VS Code)
- [ ] Includes tests for any new logic added
- [ ] No regression in snapshot/diff output format
- [ ] No hard dependency added without updating `requirements.txt`
- [ ] `GEMINI_API_KEY` read from environment — never hardcoded
- [ ] Public function signatures unchanged (see `INSTRUCTIONS.md`)
- [ ] All new functions have docstrings and type hints
