from __future__ import annotations

import os
import re
from typing import Any, List, Dict
from urllib.parse import quote_plus

try:
    import ollama
except ImportError:
    ollama = None  # type: ignore

SYSTEM_PROMPT = """You are an automated desktop agent. You receive a list of screen elements formatted as '[ID] type "name" (x,y)'.

Select the correct element ID to fulfill the user's task.
Respond with EXACTLY ONE action for the immediate next step.
Output contract (strict):
1) Output exactly one single line.
2) Do not output reasoning, explanations, markdown, code fences, bullets, or extra text.
3) Do not output multiple actions.
4) If you are uncertain, output a best single action from the allowed commands.

Allowed formats:
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
5. Use `done` ONLY when the whole user task is complete. If you just launched an app for a multi-step task, continue with the next step.

Example outputs:
launch notepad
click 12
type 5 hello world
done
"""

_VALID_PATTERNS = (
    re.compile(r"^click\s+\d+$", re.IGNORECASE),
    re.compile(r"^type\s+\d+\s+.+$", re.IGNORECASE),
    re.compile(r"^key\s+[^\s]+$", re.IGNORECASE),
    re.compile(r"^scroll\s+\d+\s+(?:up|down)$", re.IGNORECASE),
    re.compile(r"^launch\s+.+$", re.IGNORECASE),
    re.compile(r"^done$", re.IGNORECASE),
)

_chat_history: List[Dict[str, str]] = []
_pending_actions: List[str] = []
_resolved_model: str | None = None
_PREFERRED_DEFAULT_MODEL = "qwen2.5:7b"
_FALLBACK_MODELS = ("qwen2.5:3b", "gpt-oss:20b", "llama2:7b", "gemma3:1b")
_MAX_CHAT_TURNS = 6
_BROWSER_HINTS = ("brave", "chrome", "edge", "firefox", "opera", "browser")
_SITE_SEARCH_TARGETS = ("youtube", "google", "github", "wikipedia")
_WHATSAPP_HINTS = ("whatsapp",)


def _is_debug_enabled() -> bool:
    return os.getenv("HAWK_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}


def _list_installed_models() -> list[str]:
    if ollama is None:
        return []

    try:
        payload = ollama.list()
    except Exception:
        return []

    if isinstance(payload, dict):
        models = payload.get("models", [])
    elif isinstance(payload, list):
        models = payload
    else:
        models = getattr(payload, "models", [])

    names: list[str] = []
    for model in models or []:
        if isinstance(model, dict):
            name = model.get("model") or model.get("name")
        else:
            name = getattr(model, "model", None) or getattr(model, "name", None)

        if isinstance(name, str) and name and name not in names:
            names.append(name)

    return names


def _get_model() -> str:
    global _resolved_model

    if _resolved_model:
        return _resolved_model

    configured_model = os.getenv("OLLAMA_MODEL", "").strip()
    if configured_model:
        _resolved_model = configured_model
        return _resolved_model

    installed = _list_installed_models()

    if _PREFERRED_DEFAULT_MODEL in installed:
        _resolved_model = _PREFERRED_DEFAULT_MODEL
        return _resolved_model

    for candidate in _FALLBACK_MODELS:
        if candidate in installed:
            print(f"[agent] OLLAMA_MODEL not set. Using installed model '{candidate}'.")
            _resolved_model = candidate
            return _resolved_model

    if installed:
        _resolved_model = installed[0]
        print(f"[agent] OLLAMA_MODEL not set. Using first installed model '{_resolved_model}'.")
        return _resolved_model

    _resolved_model = _PREFERRED_DEFAULT_MODEL
    return _resolved_model


def _extract_action(reply: str) -> str:
    for raw_line in reply.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("```"):
            continue

        line = line.replace("`", "")
        line = line.replace("**", "")
        line = line.replace("__", "")
        line = line.strip()
        line = re.sub(r"^[-*+>]+\s*", "", line)
        line = re.sub(r"^\d+[.)]\s*", "", line)
        if not line:
            continue

        # Normalize common model formatting noise.
        line = re.sub(r"^\[(.+)\]$", r"\1", line)
        line = re.sub(r"\[(\d+)\]", r"\1", line)
        line = re.sub(r"\s*\+\s*", "+", line)
        line = re.sub(r"\s+", " ", line).strip()

        for pattern in _VALID_PATTERNS:
            match = pattern.match(line)
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


def _normalize_task_text(task: str) -> str:
    text = task.strip()
    typo_rules = (
        (r"\bbreave\b", "brave"),
        (r"\bfro\b", "for"),
        (r"\byotube\b", "youtube"),
        (r"\byou\s*tube\b", "youtube"),
    )

    for pattern, replacement in typo_rules:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    return re.sub(r"\s+", " ", text).strip()


def _truncate_query_clause(query: str) -> str:
    stop_patterns = (
        r"\s*,\s*",
        r"\s*;\s*",
        r"\s+\.\s+",
        r"\s+(?:and|then)\s+",
        r"\s+(?:in|on)\s+(?:youtube|google|github|wikipedia)\s+search\b",
    )

    trimmed = query.strip()
    for pattern in stop_patterns:
        parts = re.split(pattern, trimmed, maxsplit=1, flags=re.IGNORECASE)
        trimmed = parts[0].strip()

    return re.sub(r"[.!?]+$", "", trimmed).strip()


def _extract_site_search(task: str) -> tuple[str, str] | None:
    task_text = _normalize_task_text(task)
    patterns = (
        r"\b(?:in|on)\s+(youtube|google|github|wikipedia)\s+search\s+(?:for\s+)?(.+)$",
        r"\b(youtube|google|github|wikipedia)\s+search\s+(?:for\s+)?(.+)$",
    )

    for pattern in patterns:
        match = re.search(pattern, task_text, flags=re.IGNORECASE)
        if not match:
            continue

        site = match.group(1).lower()
        query = _truncate_query_clause(match.group(2).strip().strip('"').strip("'"))
        if query:
            return site, query

    return None


def _build_site_search_url(site: str, query: str) -> str | None:
    encoded_query = quote_plus(query)
    if site == "youtube":
        return f"https://www.youtube.com/results?search_query={encoded_query}"
    if site == "google":
        return f"https://www.google.com/search?q={encoded_query}"
    if site == "github":
        return f"https://github.com/search?q={encoded_query}"
    if site == "wikipedia":
        return f"https://en.wikipedia.org/w/index.php?search={encoded_query}"

    return None


def _extract_search_query(task: str) -> str | None:
    task_text = _normalize_task_text(task)
    patterns = (
        r"\bsearch\s+for\s+(.+)$",
        r"\bsearch\s+(.+)$",
    )

    for pattern in patterns:
        match = re.search(pattern, task_text, flags=re.IGNORECASE)
        if not match:
            continue

        query = _truncate_query_clause(match.group(1).strip().strip('"').strip("'"))
        query = re.split(
            r"\s+(?:in|on)\s+(?:brave|chrome|edge|firefox|opera|browser)\b",
            query,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0].strip()

        if query:
            return query

    return None


def _extract_message_target(task: str) -> str | None:
    task_text = _normalize_task_text(task)
    patterns = (
        r"\bsend\s+message\s+to\s+(.+?)\s+contact\b",
        r"\bsend\s+message\s+to\s+(.+?)(?:\s*,|\s+message\s+content\b|$)",
        r"\bsearch\s+for\s+contact\s*\(\s*(.+?)\s*\)",
        r"\btext\s+(.+?)\s+contact\s+.+$",
    )

    for pattern in patterns:
        match = re.search(pattern, task_text, flags=re.IGNORECASE)
        if not match:
            continue

        target = re.sub(r"\s+", " ", match.group(1).strip().strip('"').strip("'"))
        if target:
            return target

    return None


def _extract_message_content(task: str) -> str | None:
    task_text = _normalize_task_text(task)
    patterns = (
        r"\bmessage\s+content\s*\(\s*(.+?)\s*\)",
        r"\bmessage\s+content\s*[:=]\s*(.+)$",
        r"\bmessage\s+content\s+(.+)$",
        r"\btext\s+.+?\s+contact\s+(.+)$",
    )

    for pattern in patterns:
        match = re.search(pattern, task_text, flags=re.IGNORECASE)
        if not match:
            continue

        content = re.sub(r"\s+", " ", match.group(1).strip().strip('"').strip("'"))
        if content:
            return content

    return None


def _should_plan_browser_search(task: str, action: str) -> bool:
    if not action.lower().startswith("launch "):
        return False

    launched = action.split(maxsplit=1)[1].lower() if len(action.split(maxsplit=1)) > 1 else ""
    task_lower = task.lower()
    has_browser_hint = any(name in launched for name in _BROWSER_HINTS) or any(
        name in task_lower for name in _BROWSER_HINTS
    )

    has_search_intent = _extract_site_search(task) is not None or _extract_search_query(task) is not None
    return has_browser_hint and has_search_intent


def _should_plan_whatsapp_message(task: str, action: str) -> bool:
    if not action.lower().startswith("launch "):
        return False

    launched = action.split(maxsplit=1)[1].lower() if len(action.split(maxsplit=1)) > 1 else ""
    task_lower = task.lower()
    has_whatsapp_hint = any(name in launched for name in _WHATSAPP_HINTS) or any(
        name in task_lower for name in _WHATSAPP_HINTS
    )

    return (
        has_whatsapp_hint
        and _extract_message_target(task) is not None
        and _extract_message_content(task) is not None
    )


def _plan_post_launch_actions(task: str) -> List[str]:
    site_search = _extract_site_search(task)
    if site_search:
        site, query = site_search
        url = _build_site_search_url(site, query)
        if url:
            return ["key ctrl+l", f"type 0 {url}", "key enter"]

    query = _extract_search_query(task)
    if not query:
        return []

    # Deterministic browser flow: focus URL bar, type query, submit.
    return ["key ctrl+l", f"type 0 {query}", "key enter"]


def _plan_whatsapp_post_launch_actions(task: str) -> List[str]:
    target = _extract_message_target(task)
    content = _extract_message_content(task)
    if not target or not content:
        return []

    # WhatsApp desktop flow: open search, choose chat, type and send.
    return ["key ctrl+f", f"type 0 {target}", "key enter", f"type 0 {content}", "key enter"]


def _trim_chat_history(max_turns: int = _MAX_CHAT_TURNS) -> None:
    global _chat_history

    if not _chat_history:
        return

    if _chat_history[0].get("role") != "system":
        return

    max_non_system = max_turns * 2
    non_system = _chat_history[1:]
    if len(non_system) <= max_non_system:
        return

    _chat_history = [_chat_history[0], *non_system[-max_non_system:]]


def _normalize_debug_reply(reply_text: str) -> str:
    """Render escaped model newlines in logs for easier debugging."""
    return reply_text.replace("\\r\\n", "\n").replace("\\n", "\n")


def ask_agent(snapshot: str, task: str) -> str:
    """Send the snapshot to Ollama and return one validated action string."""
    global _chat_history, _pending_actions

    if _pending_actions:
        action = _pending_actions.pop(0)
        print(f"[agent] Using planned follow-up action: {action}")
        return action
    
    if ollama is None:
        print(
            "[agent] Ollama is not installed or not running. "
            "Please start Ollama and ensure your model is pulled."
        )
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
    _trim_chat_history()
    
    try:
        response = ollama.chat(
            model=_get_model(),
            messages=_chat_history,
            options={"temperature": 0.0}
        )
        reply_text = response.get('message', {}).get('content', '')
        _chat_history.append({"role": "assistant", "content": reply_text})
        _trim_chat_history()
        
        if _is_debug_enabled():
            print("-" * 40)
            print(f"[DEBUG] Ollama response:\n{_normalize_debug_reply(reply_text)}")
            print("-" * 40)

        action = _extract_action(reply_text)
        planned_followups: List[str] = []
        if _should_plan_browser_search(task, action):
            # End the loop after deterministic browser-search sequence to avoid
            # extra model-generated UI drift after query submission.
            planned_followups = _plan_post_launch_actions(task)
        elif _should_plan_whatsapp_message(task, action):
            planned_followups = _plan_whatsapp_post_launch_actions(task)

        if planned_followups:
            _pending_actions = planned_followups + ["done"]
            print(
                "[agent] Planned deterministic follow-up actions "
                f"({len(_pending_actions) - 1} step(s) + done)."
            )

        return action
    except Exception as exc:
        available_models = _list_installed_models()
        if available_models:
            available = ", ".join(available_models)
            print(
                f"[agent] Ollama error: {exc}. Available models: {available}. "
                "Set OLLAMA_MODEL to one of the available models."
            )
        else:
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
    global _chat_history, _pending_actions, _resolved_model
    _chat_history = []
    _pending_actions = []
    _resolved_model = None
