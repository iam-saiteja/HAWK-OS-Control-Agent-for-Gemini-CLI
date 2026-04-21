# Task Template for Copilot

Use this structure when implementing a new feature.

## Task
<what to build>

## Constraints
- Windows-first
- Keep perception/reasoning decoupled
- Keep model prompt action-only format

## Files Expected
- hawk/hawk.py (perception)
- hawk/bridge.py (format/diff)
- hawk/gemini_ext.py (brain + executor)
- hawk/main.py (loop)
- tests/* (coverage)

## Acceptance Checklist
- [ ] Works in local loop for at least one app (Notepad or VS Code)
- [ ] Includes tests for new logic
- [ ] No regression in snapshot/diff output format
- [ ] No hard dependency added without updating requirements.txt
