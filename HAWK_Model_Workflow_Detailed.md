# HAWK Model Workflow Documentation (Detailed)

## Purpose

This document explains, in detail, how the current HAWK runtime works from process start, to task input, to screen-state structuring, to model reasoning, to action execution, and finally to termination.

This version reflects the current Ollama-based runtime in this branch.

---

## 1. High-Level Architecture

HAWK is a hybrid system:

- Deterministic perception and formatting logic (Python code)
- A local language model for next-step reasoning (Ollama)
- Deterministic execution logic (Python code)

Core modules:

- `main.py` (root): launcher and virtual environment routing
- `hawk/main.py`: main control loop
- `hawk/hawk.py`: perception pipeline (UIA -> CDP -> OCR)
- `hawk/bridge.py`: snapshot and diff formatter with stable IDs
- `hawk/agent.py`: model interaction, action parsing, and verifier
- `hawk/executor.py`: action dispatch to mouse/keyboard automation

---

## 2. Startup Sequence

### Step 2.1 - User starts the app

Typical command:

```powershell
python main.py "open notepad and type hello world"
```

### Step 2.2 - Root launcher routes to project venv

In `main.py` (root), `_rerun_with_venv_if_needed()` checks:

1. The expected project venv Python path (`.venv/Scripts/python.exe` on Windows)
2. The currently running interpreter (`sys.executable`)
3. If they differ, it re-runs the same script and arguments using venv Python

Why this matters:

- Prevents import errors caused by running with global Python
- Makes runtime behavior consistent across machines

### Step 2.3 - Runtime loop entry

After launcher checks, root `main.py` imports `run` from `hawk.main` and calls:

```python
run(task)
```

---

## 3. Task Input and Loop Initialization

Inside `hawk/main.py`, `run(task, max_turns=25, settle_seconds=0.8)` initializes:

- `bridge = Bridge()` for state formatting and ID tracking
- `action_history = []` for verifier context
- `turn = 0`

Then:

1. `reset_chat()` clears model-side in-memory state (`_chat_history`, `_pending_actions`, cached model choice)
2. Prints task
3. Waits 3 seconds so the user can focus the target window

From here, HAWK enters the main loop (`while turn < max_turns`).

---

## 4. Perception: Taking Screen Input

Each loop turn starts with:

```python
window_title, elements = get_screen_state()
```

`hawk/hawk.py` uses a fallback chain.

### Step 4.1 - UIAutomation path (primary)

`get_active_window_tree()`:

- Imports `uiautomation` dynamically
- Reads foreground control (`GetForegroundControl()`)
- Walks UI tree recursively (`max_depth=6`)
- Extracts element fields:
  - `name`
  - `type` (`ControlTypeName`)
  - center coordinates (`x`, `y`)
- Applies DPI normalization via `_dpi_scale()`

Output type:

```python
Tuple[str, List[dict]]
```

where each element dict is conceptually:

```python
{"name": str, "type": str, "x": int, "y": int}
```

### Step 4.2 - CDP accessibility fallback

If UIA returns too few elements (threshold default `> 3`), HAWK runs `get_cdp_tree()`:

- Connects to `http://localhost:9222/json`
- Uses target websocket debugger URL
- Calls `Accessibility.enable`
- Calls `Accessibility.getFullAXTree`
- Converts nodes into element dicts

This supports Chromium/Electron targets with remote debugging enabled.

### Step 4.3 - OCR fallback

If CDP is also insufficient, HAWK runs `get_screen_text_with_coords()`:

- Captures screen via `mss`
- Reads text via `screen_ocr` (WinRT backend)
- Converts words into `TextControl` element dicts

### Step 4.4 - De-duplication

All perception branches pass through `_dedupe_elements()` so duplicate `(name, type, x, y)` items are removed.

---

## 5. Structuring Input for the Model

After perception, `hawk/main.py` decides how to build model context text.

### Step 5.1 - Empty-element handling

`run()` retries perception up to 3 times if no elements are found.

If still empty, it uses a blind-mode snapshot:

```text
WINDOW: Unknown
DIFF: No elements detected. (Blind typing allowed: type 0 <text>)
```

This keeps the loop alive and allows `type 0 ...` flows.

### Step 5.2 - Turn 0 full snapshot

On first turn (`turn == 0`), `bridge.format_snapshot(elements, window_title)` creates full context:

```text
WINDOW: <title>
[1] <class> "<name>" (x,y)
[2] <class> "<name>" (x,y)
...
```

### Step 5.3 - Later turns diff snapshot

On subsequent turns, `bridge.format_diff(...)` emits only changes:

- Added elements: `+ [id] ...`
- Removed elements: `- [id] "name" removed`
- No changes: `DIFF: no changes`

### Step 5.4 - Stable IDs and noise-resistant matching

`Bridge` computes an element key as:

```python
(name, type, x // 100, y // 100)
```

Using 100px coordinate buckets reduces false diffs from tiny UI shifts.

---

## 6. Model Input Assembly and Reasoning

Model interaction happens in `hawk/agent.py` via `ask_agent(snapshot, task)`.

### Step 6.1 - Pending deterministic actions first

Before calling the model, agent checks `_pending_actions`.

If not empty:

- Pops and returns the next planned action
- Skips model call for this turn

This is used for deterministic browser-search follow-up.

### Step 6.2 - Model selection strategy

`_get_model()` chooses model in this order:

1. `OLLAMA_MODEL` env var if set
2. Preferred default if installed (`qwen2:7b`)
3. Fallback installed models (`llama2:7b`, `gemma3:1b`)
4. First installed model from `ollama.list()`
5. Final fallback string `qwen2:7b` (if list unavailable)

### Step 6.3 - Chat history and message shape

Agent keeps `_chat_history` across turns.

- First call appends `SYSTEM_PROMPT`
- Each turn appends a user message with:
  - Original task
  - Last extracted action
  - Current screen snapshot or diff

Exact pattern:

```text
Task: <task>

Your Last Action: <last_action>

Screen Snapshot:
<snapshot>
```

### Step 6.4 - Single-action contract

`SYSTEM_PROMPT` enforces one-line action output from this set:

- `click <ID>`
- `type <ID> <text>`
- `key <combo>`
- `scroll <ID> <up|down>`
- `launch <app_name>`
- `done`

### Step 6.5 - Action extraction and sanitation

`_extract_action(reply_text)` validates model output line-by-line.

It handles common formatting noise:

- Removes backticks
- Converts `[11]` to `11`
- Normalizes spaces and key-combo separators

Then it applies strict regex patterns. If no valid line is found, it returns `done`.

---

## 7. Intent Structuring for Browser Search Tasks

This branch includes deterministic intent parsing for browser search workflows.

### Step 7.1 - Task normalization

`_normalize_task_text(task)` fixes common typos and spacing, for example:

- `breave` -> `brave`
- `yotube` -> `youtube`

### Step 7.2 - Search intent extraction

Two extractors are used:

- `_extract_site_search(task)` for clauses like:
  - `in youtube search bixi op`
  - `github search for repo xyz`
- `_extract_search_query(task)` for general search clauses:
  - `search for youtube.com`

Query text is trimmed by `_truncate_query_clause()` to remove trailing chained instructions.

### Step 7.3 - Deterministic follow-up decision

After the model returns an action, `_should_plan_browser_search(task, action)` checks:

1. Model action starts with `launch ...`
2. Task/action indicates a browser app
3. Task includes search intent

If all true, `_plan_post_launch_actions(task)` queues deterministic actions such as:

```text
key ctrl+l
type 0 <query-or-site-url>
key enter
done
```

This prevents drift after browser launch and ensures query submission completes.

---

## 8. Execution Layer

`hawk/main.py` sends the chosen action to:

```python
execute_action(action, bridge.get_elements())
```

In `hawk/executor.py`:

- `click <id>`: clicks element center
- `type <id> <text>`:
  - if id is `0`, pastes text into current focus
  - else clicks element then pastes text
- `key <combo>`: presses single key or hotkey combo
- `launch <app_name>`: Win key -> type app -> Enter -> wait
- `scroll <id> <up|down>`: scrolls near element coordinates
- `done`: returns `False` to stop loop

Safety behavior:

- `_get_element()` validates IDs
- Missing/invalid IDs log warnings and skip action
- Exceptions are caught and logged to keep loop alive

---

## 9. Progress Verification and Replanning

Every 5 turns in `hawk/main.py`, HAWK calls:

```python
verify_progress(task, action_history, snapshot)
```

`verify_progress()` in `hawk/agent.py` uses `ollama.generate(...)` with prompt context:

- Original task
- Last up to 10 actions
- Current screen snapshot/diff

Expected verifier output words:

- `CONTINUE`
- `REPLAN`
- `DONE`

Loop behavior:

- `DONE` -> stop as complete
- `REPLAN` -> force full snapshot next model call
- `CONTINUE` -> continue normally

---

## 10. Loop Exit Conditions

The run ends when any of the following occurs:

1. Executor receives `done` and returns `False`
2. Verifier returns `DONE`
3. Turn count reaches `max_turns` (default 25)

---

## 11. Error and Recovery Strategy

Current behavior is fail-soft:

- Missing optional libraries in perception branches return empty lists instead of crashing
- Ollama import failure prints guidance and returns `done`
- Ollama runtime errors print model availability hints
- Invalid model output is sanitized and defaults to `done`
- Empty screen state triggers retries and blind typing fallback snapshot

Result: the system favors controlled termination or retry over hard crashes.

---

## 12. End-to-End Data Flow (Compact)

```text
CLI task string
  -> root main.py (venv reroute)
  -> hawk.main.run(task)
  -> get_screen_state() [UIA -> CDP -> OCR]
  -> Bridge snapshot/diff text
  -> ask_agent(snapshot, task)
      -> Ollama chat
      -> _extract_action
      -> optional deterministic queue for browser search
  -> execute_action(action, elements)
  -> verify_progress every 5 turns
  -> repeat until done / verified done / max turns
```

---

## 13. What Is Deterministic vs Model-Driven

Model-driven:

- Choosing next UI action from current snapshot context
- Periodic status judgement (`CONTINUE`, `REPLAN`, `DONE`)

Deterministic:

- Perception fallback chain
- Snapshot and diff formatting
- Action validation regex rules
- Execution dispatch
- Browser launch + search follow-up sequence

This split keeps behavior interpretable and easier to debug.
