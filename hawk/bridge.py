from __future__ import annotations

from typing import Dict, Iterable, Tuple


class Bridge:
    """Formats snapshots and diffs with stable IDs across turns."""

    def __init__(self) -> None:
        self.prev_snapshot: Dict[int, dict] = {}

    def format_snapshot(self, elements: Iterable[dict], window_title: str) -> str:
        current: Dict[int, dict] = {}
        lines = [f"WINDOW: {window_title}"]

        for i, raw in enumerate(elements, 1):
            el = self._normalize(raw)
            etype = self._classify(el["type"])
            lines.append(f'[{i}] {etype} "{el["name"]}" ({el["x"]},{el["y"]})')
            current[i] = el

        self.prev_snapshot = current
        return "\n".join(lines)

    def format_diff(self, elements: Iterable[dict], window_title: str) -> str:
        curr_by_key: Dict[Tuple[str, str, int, int], dict] = {}
        ordered_keys: list[Tuple[str, str, int, int]] = []
        for raw in elements:
            el = self._normalize(raw)
            key = self._element_key(el)
            if key in curr_by_key:
                continue
            curr_by_key[key] = el
            ordered_keys.append(key)

        prev_by_key: Dict[Tuple[str, str, int, int], tuple[int, dict]] = {}
        for idx, prev_el in sorted(self.prev_snapshot.items()):
            key = self._element_key(prev_el)
            if key not in prev_by_key:
                prev_by_key[key] = (idx, prev_el)

        curr_keys = set(curr_by_key.keys())
        prev_keys = set(prev_by_key.keys())
        added = [key for key in ordered_keys if key not in prev_keys]
        removed = [key for key in prev_keys if key not in curr_keys]

        if not added and not removed:
            refreshed: Dict[int, dict] = {}
            for key, (old_id, _) in prev_by_key.items():
                refreshed[old_id] = curr_by_key[key]
            self.prev_snapshot = refreshed
            return "DIFF: no changes"

        lines = [f"WINDOW: {window_title}", "DIFF:"]
        new_snapshot: Dict[int, dict] = {}

        shared_keys = [key for key in ordered_keys if key in prev_keys]
        for key in sorted(shared_keys, key=lambda k: prev_by_key[k][0]):
            old_id, _ = prev_by_key[key]
            new_snapshot[old_id] = curr_by_key[key]

        next_id = max(self.prev_snapshot.keys(), default=0)
        for key in added:
            el = curr_by_key[key]
            next_id += 1
            new_snapshot[next_id] = el
            etype = self._classify(el["type"])
            lines.append(f'+ [{next_id}] {etype} "{el["name"]}" ({el["x"]},{el["y"]})')

        for key in sorted(removed, key=lambda k: prev_by_key[k][0]):
            old_id, old_el = prev_by_key[key]
            lines.append(f'- [{old_id}] "{old_el["name"]}" removed')

        self.prev_snapshot = new_snapshot
        return "\n".join(lines)

    def get_elements(self) -> Dict[int, dict]:
        return self.prev_snapshot

    @staticmethod
    def _normalize(el: dict) -> dict:
        return {
            "name": str(el.get("name", "")).replace('"', "'"),
            "type": str(el.get("type", "")),
            "x": int(el.get("x", 0)),
            "y": int(el.get("y", 0)),
        }

    @staticmethod
    def _element_key(el: dict) -> Tuple[str, str, int, int]:
        return (
            el["name"],
            el["type"],
            el["x"] // 100,
            el["y"] // 100,
        )

    @staticmethod
    def _classify(control_type: str) -> str:
        mapping = {
            "ButtonControl": "btn",
            "EditControl": "input",
            "TextControl": "text",
            "MenuItemControl": "menu",
            "MenuBarControl": "menu",
            "TabItemControl": "tab",
            "CheckBoxControl": "check",
            "ComboBoxControl": "select",
            "DocumentControl": "editor",
            "button": "btn",
            "textbox": "input",
            "link": "link",
            "menuitem": "menu",
        }
        return mapping.get(control_type, "el")
