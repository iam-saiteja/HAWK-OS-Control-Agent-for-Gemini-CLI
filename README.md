# HAWK — Windows OS Control Agent

> A local-first autonomous desktop control agent for Windows using structured UI perception and Ollama-powered reasoning.



---

## Overview

HAWK is an AI-powered Windows desktop automation agent designed to control applications through structured UI understanding instead of screenshot-heavy vision systems.

Unlike traditional GUI agents that depend entirely on screenshots and expensive multimodal APIs, HAWK uses:

* **UI Automation (UIA)**
* **Chrome DevTools Protocol (CDP)**
* **OCR fallback**
* **Local Ollama models**

This makes the system:

* Faster
* More lightweight
* Fully local
* Easier to debug
* More modular

---

# Why HAWK?

Most desktop AI agents rely heavily on screenshots for every reasoning step.

That creates several problems:

* Slow execution loops
* High token usage
* Expensive API costs
* Hard-to-debug reasoning pipelines
* Tight coupling between perception and planning

HAWK solves this by separating:

| Layer      | Responsibility                     |
| ---------- | ---------------------------------- |
| Perception | Extract structured UI elements     |
| Reasoning  | Decide next action using local LLM |
| Execution  | Perform mouse/keyboard actions     |

The result is a clean, pluggable architecture optimized for local execution.

---

# Core Architecture

```text
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

# Features

* Structured Windows UI extraction
* Local AI reasoning using Ollama
* OCR fallback for unsupported apps
* Stable UI element tracking across turns
* Action verification and replanning
* Blind typing fallback support
* Local-only execution (no cloud dependency)
* Lightweight modular architecture

---

# Project Structure

```text
hawk/
├── main.py        # Runtime orchestration loop
├── hawk.py        # Perception layer
├── bridge.py      # Snapshot + diff formatting
├── agent.py       # Ollama reasoning engine
├── executor.py    # Action execution layer

tests/
├── test_agent.py
├── test_bridge.py
├── test_executor.py
└── test_hawk.py
```

---

# System Workflow

HAWK operates in a continuous closed loop:

1. Extract UI elements from the active application
2. Convert elements into compact structured snapshots
3. Send context to Ollama
4. Receive exactly one next action
5. Execute the action
6. Verify progress every few turns
7. Continue, replan, or stop

---

# Layer Details

## 1. Perception Layer (`hawk.py`)

Responsible for extracting structured UI information.

### Extraction Priority

1. Windows UI Automation (UIA)
2. CDP accessibility tree
3. WinRT OCR fallback

### Capabilities

* DPI scaling normalization
* Element deduplication
* Automatic fallback handling
* Actionable element filtering

---

## 2. Bridge Layer (`bridge.py`)

Transforms raw UI elements into compact textual snapshots.

### Responsibilities

* Stable element IDs
* Delta updates between turns
* Snapshot compression
* Noise reduction using coordinate bucketing

### Example Snapshot

```text
[12] button "Send" (540,220)
[13] textbox "Search" (420,180)
```

---

## 3. Agent Layer (`agent.py`)

Handles reasoning using Ollama.

### Ollama Integration

Uses:

```python
ollama.chat(...)
ollama.generate(...)
```

### Default Model

```bash
qwen2:7b
```

Can be changed using:

```bash
OLLAMA_MODEL
```

### Supported Actions

```text
click <id>
type <id> <text>
key <combo>
scroll <id> <up|down>
launch <app_name>
done
```

### Special Features

* Blind typing support:

```text
type 0 <text>
```

* Invalid output sanitization
* Chat history persistence
* Progress verification every 5 turns

---

## 4. Execution Layer (`executor.py`)

Executes actions on the operating system.

### Technologies Used

* `pyautogui`
* `pyperclip`

### Supported Operations

* Mouse clicks
* Keyboard shortcuts
* Scrolling
* App launching
* Reliable clipboard-based text input

---

# Main Runtime Loop

Located in:

```text
hawk/main.py
```

### Runtime Behavior

* Resets chat state at task start
* Waits for active window focus
* Retries UI extraction on failure
* Falls back to blind typing mode
* Runs periodic verification checks
* Stops on:

  * `done`
  * `max_turns`

---

# Installation

## 1. Clone Repository

```bash
git clone <your-repo-url>
cd hawk
```

---

## 2. Create Virtual Environment

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

---

## 3. Install Dependencies

```bash
pip install -r requirements.txt
```

---

# Requirements

```text
uiautomation
screen-ocr[winrt]
mss
websockets
pyautogui
pyperclip
ollama
pytest
```

---

# Ollama Setup

## Install Ollama

Download and install:

* Ollama

---

## Pull a Model

```bash
ollama pull qwen2:7b
```

---

## Optional: Use Another Model

### PowerShell

```powershell
$env:OLLAMA_MODEL = "qwen2:7b"
```

---

# Running the Agent

```powershell
python -m hawk.main "open notepad and type hello world"
```

---

# Running Tests

```bash
pytest -q
```

---

# Differences From Gemini Version

Compared to the previous Gemini-based implementation:

| Gemini Version           | Ollama Version          |
| ------------------------ | ----------------------- |
| Cloud API dependency     | Fully local reasoning   |
| Google Generative AI SDK | Ollama SDK              |
| API key required         | No API key              |
| External inference       | Local inference         |
| Limited launch support   | Native `launch` action  |
| No blind typing          | `type 0 <text>` support |

---

# Design Philosophy

HAWK follows a simple principle:

> Use structured UI data whenever possible and use vision only as fallback.

This reduces unnecessary reasoning complexity while improving reliability and speed.

---

# Future Improvements

Potential future additions:

* macOS/Linux support
* Multi-monitor awareness
* Browser-native planning mode
* Memory + long-horizon task planning
* Reinforcement learning feedback loops
* Voice command integration
* Better OCR heuristics
* Safety sandboxing

---

# Example Use Cases

* Automating repetitive desktop workflows
* Local AI assistant experiments
* UI testing automation
* Research agents
* Productivity tooling
* Accessibility tooling

---

# License

MIT License

---

# Acknowledgements

Built using:

* Ollama
* Python UI Automation ecosystem
* WinRT OCR
* Chrome DevTools Protocol
