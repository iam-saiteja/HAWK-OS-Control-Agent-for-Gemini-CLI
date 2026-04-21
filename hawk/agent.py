from __future__ import annotations

import os
import re
from typing import Any, List, Dict

try:
    import ollama
except ImportError:
    ollama = None  # type: ignore

SYSTEM_PROMPT = """You are an automated desktop agent. You receive a list of screen elements formatted as '[ID] type "name" (x,y)'.

Select the correct element ID to fulfill the user's task.
Respond with EXACTLY ONE action for the immediate next step. DO NOT output a sequence of actions.
Strictly use this format:
  click <ID>
  type <ID> <text>
  key <combo>
  scroll <ID> <up|down>
  launch <app_name>
  done

RULES & CONTEXT:
1. To open an application, use the `launch <app_name>` command. This will automatically handle pressing the windows key, searching, and hitting enter for you!
2. Useful keys include: `win`, `enter`, `esc`, `tab`, `ctrl+c`, etc.
3. Output ONLY ONE single command line. No reasoning, no thoughts.
4. DO NOT use element names or coordinates, only the integer ID. `0` is allowed for blind typing.

Example outputs:
launch notepad
click 12
type 5 hello world
done
"""

_VALID_PATTERNS = (
    re.compile(r"click\s+\d+", re.IGNORECASE),
    re.compile(r"type\s+\d+\s+.+", re.IGNORECASE),
    re.compile(r"key\s+[^\s]+", re.IGNORECASE),
    re.compile(r"scroll\s+\d+\s+(?:up|down)", re.IGNORECASE),
    re.compile(r"launch\s+.+", re.IGNORECASE),
    re.compile(r"done", re.IGNORECASE),
)

_chat_history: List[Dict[str, str]] = []


def _get_model() -> str:
    return os.getenv("OLLAMA_MODEL", "qwen2:7b")


def _extract_action(reply: str) -> str:
    for raw_line in reply.splitlines():
        line = raw_line.strip().replace("`", "").strip()
        if not line:
            continue

        for pattern in _VALID_PATTERNS:
            match = pattern.search(line)
            if not match:
                continue

            extracted = match.group(0)
            parts = extracted.split(maxsplit=1)
            cmd = parts[0].lower()
            if cmd == "done":
                return "done"
            if len(parts) == 1:
                return cmd
            return f"{cmd} {parts[1]}"

    return "done"


def ask_agent(snapshot: str, task: str) -> str:
    """Send the snapshot to Ollama and return one validated action string."""
    global _chat_history
    
    if ollama is None:
        print("[agent] Error: ollama package not installed. Run 'pip install ollama'.")
        return "done"

    if not _chat_history:
        _chat_history.append({"role": "system", "content": SYSTEM_PROMPT})
        last_action = "None yet"
    else:
        # Fetch what the assistant previously decided
        last_action = _chat_history[-1].get("content", "Unknown").strip()
        last_action = _extract_action(last_action)
        
    message = f"Task: {task}\\n\\nYour Last Action: {last_action}\\n\\nScreen Snapshot:\\n{snapshot}"
    _chat_history.append({"role": "user", "content": message})
    
    try:
        response = ollama.chat(
            model=_get_model(),
            messages=_chat_history,
            options={"temperature": 0.0}
        )
        reply_text = response.get('message', {}).get('content', '')
        _chat_history.append({"role": "assistant", "content": reply_text})
        
        print("-" * 40)
        print(f"[DEBUG] Ollama response:\\n{reply_text}")
        print("-" * 40)
        
        return _extract_action(reply_text)
    except Exception as exc:
        print(f"[agent] Ollama error: {exc}. Is the Ollama app running and model pulled?")
        return "done"


def verify_progress(task: str, action_history: list[str], snapshot: str) -> str:
    """Check whether execution should continue, replan, or stop."""
    if ollama is None:
        return "CONTINUE"
        
    history = "\n".join(f"- {action}" for action in action_history[-10:])
    message = f"""Task: {task}

Actions taken so far:
{history}

Current screen:
{snapshot}

Is the task complete, still in progress, or is the agent stuck?
Reply with exactly one word: CONTINUE, REPLAN, or DONE"""

    try:
        response = ollama.generate(
            model=_get_model(),
            prompt=message,
            options={"temperature": 0.0}
        )
        reply = (response.get("response", "")).strip().upper()
        for word in ("DONE", "REPLAN", "CONTINUE"):
            if word in reply:
                return word
        return "CONTINUE"
    except Exception as exc:
        print(f"[agent] Verification error: {exc}")
        return "CONTINUE"


def reset_chat() -> None:
    """Reset chat history between tasks."""
    global _chat_history
    _chat_history = []
