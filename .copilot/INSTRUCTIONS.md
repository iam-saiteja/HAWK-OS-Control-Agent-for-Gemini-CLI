# Copilot Working Instructions for HAWK

## Objective
Build and maintain HAWK as a Windows-first OS control agent using structured perception (UIA/CDP/OCR) and a pluggable reasoning brain.

## Non-Negotiable Design Rules
1. Keep perception and reasoning decoupled.
2. Preserve the compact numbered snapshot/diff format.
3. Prefer deterministic extraction over vision models.
4. Keep the reasoning interface single-action-per-turn.
5. Maintain pluggability: swap CLI brain by changing one function.

## Current V1 Scope
- Platform: Windows
- Brain: Gemini CLI (default)
- Loop: perceive -> format -> reason -> execute -> repeat

## Output Contract (Reasoning Layer)
Return exactly one line:
- `click <id>`
- `type <id> <text>`
- `key <combo>`
- `scroll <id> <up|down>`
- `done`

No extra text.

## Coding Priorities
- Robust fallbacks: UIA -> CDP -> OCR
- Low latency per turn (<200ms target for perception)
- Token efficiency (<500 tokens/turn)
- Defensive error handling around OS integration
- Safe defaults when external tools/dependencies are unavailable

## Test Strategy
- Unit test bridge formatting and diffs.
- Unit test executor action routing.
- Keep OS integration thin and testable.

## Editing Guidelines for Future Changes
- Do not rewrite architecture unless requested.
- Keep public interfaces stable (`get_screen_state`, `Bridge`, `ask_gemini`, `execute_action`, `run`).
- Add docstrings and type hints on new public functions.
- Prefer small, isolated commits.
