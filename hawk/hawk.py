from __future__ import annotations

import asyncio
import ctypes
import importlib
import json
import urllib.request
from typing import List, Tuple


def _dpi_scale() -> float:
    try:
        return ctypes.windll.shcore.GetScaleFactorForDevice(0) / 100.0  # type: ignore[attr-defined]
    except Exception:
        return 1.0


def _get_pyautogui_screen_size() -> tuple[int, int] | None:
    try:
        pyautogui = importlib.import_module("pyautogui")
        size = pyautogui.size()
        return int(size.width), int(size.height)
    except Exception:
        return None


def _scaled_copy(elements: List[dict], scale: float) -> List[dict]:
    return [{**el, "x": int(el["x"] / scale), "y": int(el["y"] / scale)} for el in elements]


def _screen_fit_score(elements: List[dict], width: int, height: int) -> int:
    tolerance_x = max(25, int(width * 0.02))
    tolerance_y = max(25, int(height * 0.02))

    score = 0
    for el in elements:
        x = int(el.get("x", 0))
        y = int(el.get("y", 0))
        if -tolerance_x <= x <= width + tolerance_x and -tolerance_y <= y <= height + tolerance_y:
            score += 1

    return score


def _normalize_uia_coordinates(elements: List[dict], dpi_scale: float) -> List[dict]:
    """Normalize UIAutomation coordinates to pyautogui coordinate space.

    On some Windows setups, UIA coordinates are already aligned with pyautogui.
    Applying DPI division in that case shifts clicks away from targets.
    """
    if not elements or dpi_scale <= 1.0:
        return elements

    screen_size = _get_pyautogui_screen_size()
    if not screen_size:
        # Preserve legacy behavior when screen space cannot be inferred.
        return _scaled_copy(elements, dpi_scale)

    width, height = screen_size
    scaled = _scaled_copy(elements, dpi_scale)
    raw_score = _screen_fit_score(elements, width, height)
    scaled_score = _screen_fit_score(scaled, width, height)

    if scaled_score > raw_score:
        return scaled

    return elements


def _filter_uia_noise(elements: List[dict], window_title: str) -> List[dict]:
    if not elements:
        return []

    ignored_frame_types = {"WindowControl", "PaneControl", "TitleBarControl"}
    ignored_window_buttons = {"minimize", "maximize", "restore", "close"}
    title_norm = window_title.strip().lower()
    filtered: List[dict] = []

    for el in elements:
        name = str(el.get("name", "")).strip()
        ctype = str(el.get("type", "")).strip()
        name_norm = name.lower()

        if not name:
            continue

        if title_norm and name_norm == title_norm and ctype in ignored_frame_types:
            continue

        if ctype == "ButtonControl" and name_norm in ignored_window_buttons:
            continue

        filtered.append(el)

    return filtered


def _extract_ocr_elements(result: object, offset_x: int = 0, offset_y: int = 0) -> List[dict]:
    elements: List[dict] = []
    lines = getattr(getattr(result, "result", None), "lines", [])

    for line in lines or []:
        for word in getattr(line, "words", []) or []:
            text = str(getattr(word, "text", "")).strip()
            if not text:
                continue

            left = float(getattr(word, "left", 0))
            top = float(getattr(word, "top", 0))
            width = float(getattr(word, "width", 0))
            height = float(getattr(word, "height", 0))

            elements.append(
                {
                    "name": text,
                    "type": "TextControl",
                    "x": int(offset_x + left + width / 2),
                    "y": int(offset_y + top + height / 2),
                }
            )

    return elements


def _create_ocr_reader(screen_ocr_module):
    """Create OCR reader with backend fallback for broader Windows compatibility."""
    for backend in ("winrt", None):
        try:
            if backend is None:
                return screen_ocr_module.Reader.create_quality_reader()
            return screen_ocr_module.Reader.create_quality_reader(backend=backend)
        except Exception:
            continue

    return None


def get_active_window_tree(max_depth: int = 6) -> Tuple[str, List[dict]]:
    try:
        auto = importlib.import_module("uiautomation")
    except Exception:
        return "Unknown", []

    win = auto.GetForegroundControl()
    title = getattr(win, "Name", "Unknown") or "Unknown"
    elements: List[dict] = []

    def walk(ctrl, depth: int = 0) -> None:
        if depth > max_depth:
            return

        try:
            name = ctrl.Name
            ctype = ctrl.ControlTypeName
            rect = ctrl.BoundingRectangle
            if name and rect.width() > 0 and rect.height() > 0:
                x = int(rect.left + rect.width() // 2)
                y = int(rect.top + rect.height() // 2)
                elements.append({"name": name, "type": ctype, "x": x, "y": y})
        except Exception:
            pass

        try:
            for child in ctrl.GetChildren():
                walk(child, depth + 1)
        except Exception:
            return

    walk(win)
    normalized = _normalize_uia_coordinates(elements, _dpi_scale())
    return title, _dedupe_elements(normalized)


async def get_cdp_tree(port: int = 9222) -> List[dict]:
    try:
        websockets = importlib.import_module("websockets")
    except Exception:
        return []

    try:
        targets_raw = urllib.request.urlopen(f"http://localhost:{port}/json", timeout=1).read()
        targets = json.loads(targets_raw)
        if not targets:
            return []

        ws_url = targets[0]["webSocketDebuggerUrl"]

        async with websockets.connect(ws_url) as ws:
            await ws.send(json.dumps({"id": 1, "method": "Accessibility.enable"}))
            await ws.recv()

            await ws.send(json.dumps({"id": 2, "method": "Accessibility.getFullAXTree"}))
            result = json.loads(await ws.recv())
            nodes = result.get("result", {}).get("nodes", [])

        elements: List[dict] = []
        for n in nodes:
            role = (n.get("role") or {}).get("value", "")
            name = (n.get("name") or {}).get("value", "")
            if not name:
                continue
            elements.append({"name": name, "type": role or "cdp", "x": 0, "y": 0})

        return _dedupe_elements(elements)
    except Exception:
        return []


def get_screen_text_with_coords() -> List[dict]:
    try:
        mss = importlib.import_module("mss")
        screen_ocr = importlib.import_module("screen_ocr")
    except Exception:
        return []

    try:
        reader = _create_ocr_reader(screen_ocr)
        if reader is None:
            return []

        all_elements: List[dict] = []
        with mss.mss() as sct:
            monitors = sct.monitors[1:] if len(sct.monitors) > 1 else sct.monitors
            for monitor in monitors:
                shot = sct.grab(monitor)
                offset_x = int(monitor.get("left", 0))
                offset_y = int(monitor.get("top", 0))

                result = reader.read_image(shot)
                all_elements.extend(_extract_ocr_elements(result, offset_x=offset_x, offset_y=offset_y))

        normalized = _normalize_uia_coordinates(all_elements, _dpi_scale())
        return _dedupe_elements(normalized)
    except Exception:
        return []


def get_screen_state(threshold: int = 3) -> Tuple[str, List[dict]]:
    title, uia_nodes = get_active_window_tree()
    uia_nodes = _filter_uia_noise(uia_nodes, title)
    if len(uia_nodes) > threshold:
        return title, uia_nodes

    ocr_nodes = get_screen_text_with_coords()
    if uia_nodes and ocr_nodes:
        merged_nodes = _dedupe_elements(uia_nodes + ocr_nodes)
        if len(merged_nodes) > threshold:
            return title, merged_nodes

    if len(ocr_nodes) > threshold:
        return title, ocr_nodes

    # CDP nodes often do not include actionable click coordinates.
    cdp_nodes = asyncio.run(get_cdp_tree())
    if len(cdp_nodes) > threshold and not ocr_nodes:
        return title, cdp_nodes

    if ocr_nodes:
        return title, ocr_nodes

    if uia_nodes:
        return title, uia_nodes

    return title, cdp_nodes


def _dedupe_elements(elements: List[dict]) -> List[dict]:
    seen = set()
    out = []
    for el in elements:
        sig = (el.get("name"), el.get("type"), el.get("x"), el.get("y"))
        if sig in seen:
            continue
        seen.add(sig)
        out.append(el)
    return out
