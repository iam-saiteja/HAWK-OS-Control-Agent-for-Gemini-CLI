from __future__ import annotations

import os
import re
from typing import Any, Optional, Protocol, cast

try:
    import google.generativeai as genai
except Exception:
    genai = None


class ChatSession(Protocol):
    """Minimal chat interface used by the agent."""

    def send_message(self, message: str) -> Any:
        ...


class ChatModel(Protocol):
    """Minimal model interface used to create chat sessions."""

    def start_chat(self, history: list[Any]) -> ChatSession:
        ...


SYSTEM_PROMPT = """You control a Windows computer. Each turn you receive the current screen state.

Respond with EXACTLY ONE action on a single line:
  click <id>
  type <id> <text>
  key <combo>
  scroll <id> <up|down>
  done

Nothing else. No explanation. One line only."""


_VALID_PATTERNS = (
    re.compile(r"^click\s+\d+$", re.IGNORECASE),
    re.compile(r"^type\s+\d+\s+.+$", re.IGNORECASE),
    re.compile(r"^key\s+[^\s]+$", re.IGNORECASE),
    re.compile(r"^scroll\s+\d+\s+(up|down)$", re.IGNORECASE),
    re.compile(r"^done$", re.IGNORECASE),
)

_model: Optional[ChatModel] = None
_chat: Optional[ChatSession] = None


def _ensure_chat() -> ChatSession:
    global _model, _chat

    if genai is None:
        raise RuntimeError("google-generativeai is not installed.")

    if _model is None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not set.")

        configure_fn = getattr(genai, "configure", None)
        model_cls = getattr(genai, "GenerativeModel", None)
        if not callable(configure_fn) or model_cls is None:
            raise RuntimeError("google-generativeai SDK is missing required APIs.")

        configure_fn(api_key=api_key)
        model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        _model = cast(ChatModel, model_cls(model_name, system_instruction=SYSTEM_PROMPT))

    if _chat is None:
        _chat = _model.start_chat(history=[])

    return _chat


def _extract_action(reply: str) -> str:
    for raw_line in reply.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        for pattern in _VALID_PATTERNS:
            if not pattern.match(line):
                continue

            parts = line.split(maxsplit=1)
            cmd = parts[0].lower()
            if cmd == "done":
                return "done"
            if len(parts) == 1:
                return cmd
            return f"{cmd} {parts[1]}"

    return "done"


def ask_agent(snapshot: str, task: str) -> str:
    """Send the snapshot to Gemini and return one validated action string."""
    message = f"Task: {task}\n\nScreen:\n{snapshot}"
    try:
        chat = _ensure_chat()
        response = chat.send_message(message)
        text = getattr(response, "text", "") or ""
        return _extract_action(text)
    except Exception as exc:
        print(f"[agent] Gemini error: {exc}")
        return "done"


def verify_progress(task: str, action_history: list[str], snapshot: str) -> str:
    """Check whether execution should continue, replan, or stop."""
    history = "\n".join(f"- {action}" for action in action_history[-10:])
    message = f"""Task: {task}

Actions taken so far:
{history}

Current screen:
{snapshot}

Is the task complete, still in progress, or is the agent stuck?
Reply with exactly one word: CONTINUE, REPLAN, or DONE"""

    try:
        chat = _ensure_chat()
        response = chat.send_message(message)
        reply = (getattr(response, "text", "") or "").strip().upper()
        for word in ("DONE", "REPLAN", "CONTINUE"):
            if word in reply:
                return word
        return "CONTINUE"
    except Exception:
        return "CONTINUE"


def reset_chat() -> None:
    """Reset chat history between tasks."""
    global _chat
    _chat = None
