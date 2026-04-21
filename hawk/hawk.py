from __future__ import annotations

import asyncio
import ctypes
import importlib
import json
import urllib.request
from typing import Dict, List, Tuple


def _dpi_scale() -> float:
    try:
        return ctypes.windll.shcore.GetScaleFactorForDevice(0) / 100.0  # type: ignore[attr-defined]
    except Exception:
        return 1.0


def get_active_window_tree(max_depth: int = 6) -> Tuple[str, List[dict]]:
    try:
        auto = importlib.import_module("uiautomation")
    except Exception:
        return "Unknown", []

    win = auto.GetForegroundControl()
    title = getattr(win, "Name", "Unknown") or "Unknown"
    elements: List[dict] = []
    scale = _dpi_scale()

    def walk(ctrl, depth: int = 0) -> None:
        if depth > max_depth:
            return

        try:
            name = ctrl.Name
            ctype = ctrl.ControlTypeName
            rect = ctrl.BoundingRectangle
            if name and rect.width() > 0 and rect.height() > 0:
                x = int((rect.left + rect.width() // 2) / scale)
                y = int((rect.top + rect.height() // 2) / scale)
                elements.append({"name": name, "type": ctype, "x": x, "y": y})
        except Exception:
            pass

        try:
            for child in ctrl.GetChildren():
                walk(child, depth + 1)
        except Exception:
            return

    walk(win)
    return title, _dedupe_elements(elements)


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
        reader = screen_ocr.Reader.create_quality_reader(backend="winrt")
        with mss.mss() as sct:
            shot = sct.grab(sct.monitors[0])

        result = reader.read_image(shot)
        elements: List[dict] = []
        for line in result.result.lines:
            for w in line.words:
                elements.append(
                    {
                        "name": w.text,
                        "type": "TextControl",
                        "x": int(w.left + w.width / 2),
                        "y": int(w.top + w.height / 2),
                    }
                )
        return _dedupe_elements(elements)
    except Exception:
        return []


def get_screen_state(threshold: int = 3) -> Tuple[str, List[dict]]:
    title, els = get_active_window_tree()
    if len(els) > threshold:
        return title, els

    cdp_nodes = asyncio.run(get_cdp_tree())
    if len(cdp_nodes) > threshold:
        return title, cdp_nodes

    ocr_nodes = get_screen_text_with_coords()
    return title, ocr_nodes


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
