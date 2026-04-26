from __future__ import annotations

import queue

import hawk.gui as gui_module


def test_queue_text_writer_buffers_partial_lines() -> None:
    output_queue: queue.Queue[str | object] = queue.Queue()
    writer = gui_module._QueueTextWriter(output_queue)

    writer.write("hello ")
    writer.write("world\nnext")
    writer.flush()

    assert output_queue.get_nowait() == "hello world\n"
    assert output_queue.get_nowait() == "next"


def test_worker_task_emits_completion_sentinel(monkeypatch) -> None:
    output_queue: queue.Queue[str | object] = queue.Queue()
    monkeypatch.setattr(gui_module, "run_hawk", lambda *args, **kwargs: None)

    gui_module._worker_task("open notepad", output_queue)

    assert output_queue.get_nowait() is gui_module._QUEUE_SENTINEL


def test_resolve_runtime_profile_defaults_to_balanced() -> None:
    profile = gui_module._resolve_runtime_profile("unknown")

    assert profile == gui_module._RUNTIME_PROFILES["Balanced"]


def test_format_elapsed_supports_hour_boundary() -> None:
    assert gui_module._format_elapsed(3661) == "01:01:01"