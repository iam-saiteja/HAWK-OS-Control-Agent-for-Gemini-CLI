from hawk.executor import _get_element, _resolve_cursor_point, execute_action


def test_execute_action_done() -> None:
    assert execute_action("done", {}) is False


def test_execute_action_unknown_keeps_loop() -> None:
    assert execute_action("noop", {}) is True


def test_resolve_cursor_point_keeps_in_bounds(monkeypatch) -> None:
    monkeypatch.setattr("hawk.executor.pyautogui.size", lambda: (1920, 1080))
    assert _resolve_cursor_point(100, 200) == (100, 200)


def test_resolve_cursor_point_scales_to_match_screen(monkeypatch) -> None:
    monkeypatch.setattr("hawk.executor.pyautogui.size", lambda: (1536, 864))
    assert _resolve_cursor_point(1776, 21) == (1420, 16)


def test_get_element_rejects_coordinate_free_cdp() -> None:
    parts = ["click", "1"]
    elements = {1: {"name": "Search", "type": "cdp", "x": 0, "y": 0}}
    assert _get_element(parts, elements) is None
