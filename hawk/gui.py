from __future__ import annotations

import contextlib
import queue
import threading
import time
from dataclasses import dataclass
from typing import Any

try:
    import tkinter as tk
    from tkinter import messagebox, scrolledtext, ttk
except ImportError as exc:  # pragma: no cover - platform dependency
    raise RuntimeError("Tkinter is required to use the HAWK GUI") from exc

from .main import run as run_hawk


_QUEUE_SENTINEL = object()
_RUNTIME_PROFILES: dict[str, dict[str, float | int]] = {
    "Fast": {"focus_delay": 0.5, "empty_retry_delay": 0.25, "empty_retry_limit": 3},
    "Balanced": {"focus_delay": 1.2, "empty_retry_delay": 0.4, "empty_retry_limit": 4},
    "Safe": {"focus_delay": 3.0, "empty_retry_delay": 0.8, "empty_retry_limit": 5},
}
_QUICK_TASKS = (
    "open notepad and type hello world",
    "open calculator",
    "open brave and search for github",
    "open whatsapp",
)


class _QueueTextWriter:
    def __init__(self, output_queue: queue.Queue[str | object]) -> None:
        self._queue = output_queue
        self._buffer = ""

    def write(self, text: str) -> int:
        if not text:
            return 0

        self._buffer += text
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            self._queue.put(line + "\n")

        return len(text)

    def flush(self) -> None:
        if self._buffer:
            self._queue.put(self._buffer)
            self._buffer = ""


@dataclass(slots=True)
class _RunRequest:
    task: str
    runtime_profile: str = "Balanced"
    max_turns: int = 25


def _resolve_runtime_profile(profile_name: str) -> dict[str, float | int]:
    profile = _RUNTIME_PROFILES.get(profile_name)
    if profile:
        return dict(profile)

    return dict(_RUNTIME_PROFILES["Balanced"])


def _format_elapsed(total_seconds: float) -> str:
    bounded = max(0, int(total_seconds))
    minutes, seconds = divmod(bounded, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    return f"{minutes:02d}:{seconds:02d}"


def _worker_task(run_request: _RunRequest | str, output_queue: queue.Queue[str | object]) -> None:
    request = run_request if isinstance(run_request, _RunRequest) else _RunRequest(task=run_request)
    writer = _QueueTextWriter(output_queue)
    profile_kwargs = _resolve_runtime_profile(request.runtime_profile)
    try:
        with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
            run_hawk(request.task, max_turns=request.max_turns, **profile_kwargs)
    except Exception as exc:
        output_queue.put(f"[gui] Unhandled error: {exc}\n")
    finally:
        writer.flush()
        output_queue.put(_QUEUE_SENTINEL)


class HAWKGui:
    def __init__(self, root: tk.Tk, initial_task: str) -> None:
        self.root = root
        self.root.title("HAWK Control Center")
        self.root.geometry("1060x700")
        self.root.minsize(840, 580)

        self._queue: queue.Queue[str | object] = queue.Queue()
        self._worker: threading.Thread | None = None
        self._running = False
        self._start_time: float | None = None
        self._pulse_index = 0
        self._run_count = 0
        self._history: list[str] = []

        self.task_var = tk.StringVar(value=initial_task)
        self.status_var = tk.StringVar(value="Idle")
        self.elapsed_var = tk.StringVar(value="Elapsed: 00:00")
        self.run_count_var = tk.StringVar(value="Runs: 0")
        self.profile_var = tk.StringVar(value="Balanced")
        self.max_turns_var = tk.IntVar(value=25)
        self.auto_scroll_var = tk.BooleanVar(value=True)

        self._build_ui()
        self._bind_shortcuts()
        self.root.after(100, self._drain_queue)
        self.root.after(250, self._tick_status)

    def _build_ui(self) -> None:
        self.root.configure(bg="#10141c")

        outer = tk.Frame(self.root, bg="#10141c", padx=18, pady=18)
        outer.pack(fill="both", expand=True)

        header = tk.Frame(outer, bg="#10141c")
        header.pack(fill="x", pady=(0, 14))

        title = tk.Label(
            header,
            text="HAWK Control Center",
            fg="#f5f7fb",
            bg="#10141c",
            font=("Segoe UI", 20, "bold"),
        )
        title.pack(anchor="w")

        subtitle = tk.Label(
            header,
            text="Launch tasks without disturbing the automation loop.",
            fg="#9aa7bd",
            bg="#10141c",
            font=("Segoe UI", 10),
        )
        subtitle.pack(anchor="w", pady=(4, 0))

        form = tk.Frame(outer, bg="#17202b", bd=0, highlightthickness=1, highlightbackground="#253244")
        form.pack(fill="x", pady=(0, 14))

        form_inner = tk.Frame(form, bg="#17202b", padx=14, pady=14)
        form_inner.pack(fill="x")

        tk.Label(
            form_inner,
            text="Task",
            fg="#dce6f2",
            bg="#17202b",
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w")

        self.task_entry = tk.Entry(
            form_inner,
            textvariable=self.task_var,
            bg="#0f1620",
            fg="#f5f7fb",
            insertbackground="#f5f7fb",
            relief="flat",
            font=("Segoe UI", 11),
        )
        self.task_entry.pack(fill="x", pady=(8, 0), ipady=8)

        quick_row = tk.Frame(form_inner, bg="#17202b")
        quick_row.pack(fill="x", pady=(10, 0))

        tk.Label(
            quick_row,
            text="Quick Tasks",
            fg="#9fb0c8",
            bg="#17202b",
            font=("Segoe UI", 9),
        ).pack(side="left")

        for task in _QUICK_TASKS:
            button = tk.Button(
                quick_row,
                text=task.split(" and ")[0],
                command=lambda value=task: self._set_task(value),
                bg="#1e2b3a",
                fg="#d7e3f0",
                activebackground="#2a3a4e",
                activeforeground="#ffffff",
                relief="flat",
                font=("Segoe UI", 9),
                padx=10,
                pady=4,
            )
            button.pack(side="left", padx=(8, 0))

        profile_row = tk.Frame(form_inner, bg="#17202b")
        profile_row.pack(fill="x", pady=(12, 0))

        tk.Label(
            profile_row,
            text="Runtime",
            fg="#dce6f2",
            bg="#17202b",
            font=("Segoe UI", 10, "bold"),
        ).pack(side="left")

        self.profile_combo = ttk.Combobox(
            profile_row,
            textvariable=self.profile_var,
            values=list(_RUNTIME_PROFILES.keys()),
            width=12,
            state="readonly",
        )
        self.profile_combo.pack(side="left", padx=(10, 14))

        tk.Label(
            profile_row,
            text="Max Turns",
            fg="#dce6f2",
            bg="#17202b",
            font=("Segoe UI", 10, "bold"),
        ).pack(side="left")

        self.max_turns_spinbox = tk.Spinbox(
            profile_row,
            from_=5,
            to=80,
            textvariable=self.max_turns_var,
            width=5,
            bg="#0f1620",
            fg="#f5f7fb",
            insertbackground="#f5f7fb",
            relief="flat",
            font=("Segoe UI", 10),
        )
        self.max_turns_spinbox.pack(side="left", padx=(10, 0), ipady=2)

        controls = tk.Frame(form_inner, bg="#17202b")
        controls.pack(fill="x", pady=(12, 0))

        self.run_button = tk.Button(
            controls,
            text="Run",
            command=self._start_task,
            bg="#2f7cf6",
            fg="#ffffff",
            activebackground="#1f67d8",
            activeforeground="#ffffff",
            relief="flat",
            font=("Segoe UI", 10, "bold"),
            padx=16,
            pady=8,
        )
        self.run_button.pack(side="left")

        clear_button = tk.Button(
            controls,
            text="Clear Log",
            command=self._clear_log,
            bg="#243244",
            fg="#e7eef9",
            activebackground="#314055",
            activeforeground="#ffffff",
            relief="flat",
            font=("Segoe UI", 10),
            padx=16,
            pady=8,
        )
        clear_button.pack(side="left", padx=(10, 0))

        copy_button = tk.Button(
            controls,
            text="Copy Log",
            command=self._copy_log,
            bg="#243244",
            fg="#e7eef9",
            activebackground="#314055",
            activeforeground="#ffffff",
            relief="flat",
            font=("Segoe UI", 10),
            padx=16,
            pady=8,
        )
        copy_button.pack(side="left", padx=(10, 0))

        auto_scroll = tk.Checkbutton(
            controls,
            text="Auto-scroll",
            variable=self.auto_scroll_var,
            fg="#c9d7ea",
            bg="#17202b",
            activebackground="#17202b",
            activeforeground="#ffffff",
            selectcolor="#17202b",
            font=("Segoe UI", 10),
        )
        auto_scroll.pack(side="left", padx=(10, 0))

        self.spinner = ttk.Progressbar(controls, mode="indeterminate", length=120)
        self.spinner.pack(side="left", padx=(10, 0))

        self.status_dot = tk.Canvas(controls, width=14, height=14, bg="#17202b", highlightthickness=0)
        self.status_dot.pack(side="right", padx=(8, 0))
        self._status_dot_oval = self.status_dot.create_oval(2, 2, 12, 12, fill="#6c7a90", outline="#6c7a90")

        run_count = tk.Label(
            controls,
            textvariable=self.run_count_var,
            fg="#9aa7bd",
            bg="#17202b",
            font=("Segoe UI", 10),
        )
        run_count.pack(side="right", padx=(12, 0))

        elapsed = tk.Label(
            controls,
            textvariable=self.elapsed_var,
            fg="#9aa7bd",
            bg="#17202b",
            font=("Segoe UI", 10),
        )
        elapsed.pack(side="right", padx=(12, 0))

        status = tk.Label(
            controls,
            textvariable=self.status_var,
            fg="#9aa7bd",
            bg="#17202b",
            font=("Segoe UI", 10),
        )
        status.pack(side="right")

        content = tk.Frame(outer, bg="#10141c")
        content.pack(fill="both", expand=True)

        log_frame = tk.Frame(content, bg="#10141c", bd=0, highlightthickness=1, highlightbackground="#253244")
        log_frame.pack(fill="both", expand=True, side="left")

        self.log_widget = scrolledtext.ScrolledText(
            log_frame,
            wrap="word",
            bg="#0b1118",
            fg="#dbe7f3",
            insertbackground="#f5f7fb",
            relief="flat",
            font=("Consolas", 10),
            padx=12,
            pady=12,
        )
        self.log_widget.pack(fill="both", expand=True)
        self.log_widget.tag_configure("hawk", foreground="#9de1ff")
        self.log_widget.tag_configure("agent", foreground="#ffd28d")
        self.log_widget.tag_configure("executor", foreground="#ff9ea3")
        self.log_widget.tag_configure("gui", foreground="#9ee6a4")
        self.log_widget.tag_configure("default", foreground="#dbe7f3")
        self.log_widget.configure(state="disabled")

        history_frame = tk.Frame(content, bg="#17202b", width=240, bd=0, highlightthickness=1, highlightbackground="#253244")
        history_frame.pack(fill="y", side="left", padx=(12, 0))
        history_frame.pack_propagate(False)

        tk.Label(
            history_frame,
            text="Recent Tasks",
            fg="#dce6f2",
            bg="#17202b",
            font=("Segoe UI", 10, "bold"),
            padx=10,
            pady=10,
        ).pack(anchor="w")

        self.history_list = tk.Listbox(
            history_frame,
            bg="#0f1620",
            fg="#e7eef9",
            selectbackground="#2f7cf6",
            selectforeground="#ffffff",
            relief="flat",
            font=("Segoe UI", 10),
        )
        self.history_list.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.history_list.bind("<Double-Button-1>", self._on_history_pick)

    def _bind_shortcuts(self) -> None:
        self.root.bind("<Control-Return>", self._on_run_shortcut)
        self.root.bind("<Control-l>", self._on_clear_shortcut)
        self.task_entry.bind("<Return>", self._on_run_shortcut)

    def _on_run_shortcut(self, event: Any) -> str:
        self._start_task()
        return "break"

    def _on_clear_shortcut(self, event: Any) -> str:
        self._clear_log()
        return "break"

    def _set_task(self, task: str) -> None:
        self.task_var.set(task)
        self.task_entry.focus_set()

    def _on_history_pick(self, event: Any) -> None:
        selection = self.history_list.curselection()
        if not selection:
            return

        task = self.history_list.get(selection[0])
        self._set_task(task)

    def _push_history(self, task: str) -> None:
        if task in self._history:
            self._history.remove(task)
        self._history.insert(0, task)
        self._history = self._history[:25]

        self.history_list.delete(0, "end")
        for item in self._history:
            self.history_list.insert("end", item)

    @staticmethod
    def _log_tag_for_text(text: str) -> str:
        lowered = text.lstrip().lower()
        if lowered.startswith("[hawk]"):
            return "hawk"
        if lowered.startswith("[agent]"):
            return "agent"
        if lowered.startswith("[executor]"):
            return "executor"
        if lowered.startswith("[gui]"):
            return "gui"
        return "default"

    def _append_log(self, text: str) -> None:
        self.log_widget.configure(state="normal")
        self.log_widget.insert("end", text, self._log_tag_for_text(text))
        if self.auto_scroll_var.get():
            self.log_widget.see("end")
        self.log_widget.configure(state="disabled")

    def _clear_log(self) -> None:
        self.log_widget.configure(state="normal")
        self.log_widget.delete("1.0", "end")
        self.log_widget.configure(state="disabled")

    def _copy_log(self) -> None:
        data = self.log_widget.get("1.0", "end").strip()
        if not data:
            return

        self.root.clipboard_clear()
        self.root.clipboard_append(data)
        self._append_log("[gui] Log copied to clipboard.\n")

    def _set_running_state(self, running: bool) -> None:
        self._running = running
        self.run_button.configure(state="disabled" if running else "normal")
        self.task_entry.configure(state="disabled" if running else "normal")
        self.profile_combo.configure(state="disabled" if running else "readonly")
        self.max_turns_spinbox.configure(state="disabled" if running else "normal")

        if running:
            self.spinner.start(10)
            self.status_dot.itemconfigure(self._status_dot_oval, fill="#2f7cf6", outline="#2f7cf6")
        else:
            self.spinner.stop()
            self.status_dot.itemconfigure(self._status_dot_oval, fill="#6c7a90", outline="#6c7a90")

    def _start_task(self) -> None:
        if self._running:
            return

        task = self.task_var.get().strip()
        if not task:
            messagebox.showwarning("HAWK", "Enter a task before starting the run.")
            return

        max_turns = self.max_turns_var.get()
        if max_turns < 1:
            messagebox.showwarning("HAWK", "Max turns must be greater than 0.")
            return

        self._set_running_state(True)
        self._start_time = time.monotonic()
        self._pulse_index = 0
        self.status_var.set("Running")
        self.elapsed_var.set("Elapsed: 00:00")
        self._run_count += 1
        self.run_count_var.set(f"Runs: {self._run_count}")
        self._push_history(task)

        profile = self.profile_var.get().strip() or "Balanced"
        request = _RunRequest(task=task, runtime_profile=profile, max_turns=max_turns)
        self._append_log(
            f"[gui] Starting task: {task} | profile={request.runtime_profile} | max_turns={request.max_turns}\n"
        )

        self._worker = threading.Thread(target=_worker_task, args=(request, self._queue), daemon=True)
        self._worker.start()

    def _tick_status(self) -> None:
        if self._running and self._start_time is not None:
            elapsed = time.monotonic() - self._start_time
            self.elapsed_var.set(f"Elapsed: {_format_elapsed(elapsed)}")
            pulse = ("", " .", " ..", " ...")[self._pulse_index % 4]
            self.status_var.set(f"Running{pulse}")
            self._pulse_index += 1

        self.root.after(250, self._tick_status)

    def _drain_queue(self) -> None:
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                break

            if item is _QUEUE_SENTINEL:
                elapsed = 0.0
                if self._start_time is not None:
                    elapsed = time.monotonic() - self._start_time
                self._set_running_state(False)
                self.status_var.set("Idle")
                self.elapsed_var.set(f"Last run: {_format_elapsed(elapsed)}")
                self._start_time = None
                self._append_log("[gui] Run finished.\n")
                continue

            self._append_log(str(item))

        self.root.after(100, self._drain_queue)


def launch_gui(initial_task: str = "open notepad and type hello world") -> None:
    root = tk.Tk()
    HAWKGui(root, initial_task)
    root.mainloop()