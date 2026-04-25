from hawk.hawk import (
    _dedupe_elements,
    _extract_ocr_elements,
    _filter_uia_noise,
    _normalize_uia_coordinates,
)


def test_dedupe_elements() -> None:
    elements = [
        {"name": "A", "type": "ButtonControl", "x": 1, "y": 1},
        {"name": "A", "type": "ButtonControl", "x": 1, "y": 1},
        {"name": "B", "type": "EditControl", "x": 2, "y": 2},
    ]

    deduped = _dedupe_elements(elements)
    assert len(deduped) == 2


def test_normalize_uia_coordinates_keeps_aligned_space(monkeypatch) -> None:
    elements = [{"name": "Minimize", "type": "ButtonControl", "x": 1776, "y": 21}]

    monkeypatch.setattr("hawk.hawk._get_pyautogui_screen_size", lambda: (1920, 1080))

    normalized = _normalize_uia_coordinates(elements, dpi_scale=1.25)
    assert normalized == elements


def test_normalize_uia_coordinates_scales_when_needed(monkeypatch) -> None:
    elements = [{"name": "Minimize", "type": "ButtonControl", "x": 1776, "y": 21}]

    monkeypatch.setattr("hawk.hawk._get_pyautogui_screen_size", lambda: (1536, 864))

    normalized = _normalize_uia_coordinates(elements, dpi_scale=1.25)
    assert normalized == [{"name": "Minimize", "type": "ButtonControl", "x": 1420, "y": 16}]


def test_filter_uia_noise_removes_frame_controls() -> None:
    elements = [
        {
            "name": "My App",
            "type": "WindowControl",
            "x": 400,
            "y": 300,
        },
        {
            "name": "Close",
            "type": "ButtonControl",
            "x": 790,
            "y": 12,
        },
        {
            "name": "Search",
            "type": "EditControl",
            "x": 200,
            "y": 100,
        },
    ]

    filtered = _filter_uia_noise(elements, window_title="My App")
    assert filtered == [{"name": "Search", "type": "EditControl", "x": 200, "y": 100}]


def test_extract_ocr_elements_applies_monitor_offsets() -> None:
    class Word:
        def __init__(self, text: str, left: float, top: float, width: float, height: float) -> None:
            self.text = text
            self.left = left
            self.top = top
            self.width = width
            self.height = height

    class Line:
        def __init__(self, words: list[Word]) -> None:
            self.words = words

    class ResultRoot:
        def __init__(self, lines: list[Line]) -> None:
            self.lines = lines

    class ReadResult:
        def __init__(self, lines: list[Line]) -> None:
            self.result = ResultRoot(lines)

    result = ReadResult([Line([Word("BHD", left=10, top=20, width=30, height=10)])])
    elements = _extract_ocr_elements(result, offset_x=100, offset_y=50)

    assert elements == [{"name": "BHD", "type": "TextControl", "x": 125, "y": 75}]
