from __future__ import annotations

from typing import Dict, Iterable, List, Tuple


class Bridge:
    """Formats element snapshots for the reasoning model and computes turn diffs."""

    def __init__(self) -> None:
        self.prev_elements: Dict[int, dict] = {}

    def format_snapshot(self, elements: Iterable[dict], window_title: str) -> Tuple[str, Dict[int, dict]]:
        indexed = self._index_elements(elements)
        lines: List[str] = [f"WINDOW: {window_title}"]

        for i, el in indexed.items():
            etype = self._classify(el.get("type", ""))
            name = str(el.get("name", "")).replace('"', "'")
            x, y = int(el.get("x", 0)), int(el.get("y", 0))
            lines.append(f'[{i}] {etype} "{name}" ({x},{y})')

        self.prev_elements = indexed
        return "\n".join(lines), indexed

    def format_diff(self, elements: Iterable[dict], window_title: str) -> Tuple[str, Dict[int, dict]]:
        indexed = self._index_elements(elements)
        current_signatures = {idx: self._signature(el) for idx, el in indexed.items()}
        previous_signatures = {idx: self._signature(el) for idx, el in self.prev_elements.items()}

        added = [idx for idx, sig in current_signatures.items() if sig not in previous_signatures.values()]
        removed = [idx for idx, sig in previous_signatures.items() if sig not in current_signatures.values()]

        lines: List[str] = [f"WINDOW: {window_title}", "DIFF:"]

        for i in added:
            el = indexed[i]
            etype = self._classify(el.get("type", ""))
            name = str(el.get("name", "")).replace('"', "'")
            x, y = int(el.get("x", 0)), int(el.get("y", 0))
            lines.append(f'+ [{i}] {etype} "{name}" ({x},{y})')

        for old_idx in removed:
            old_el = self.prev_elements[old_idx]
            etype = self._classify(old_el.get("type", ""))
            name = str(old_el.get("name", "")).replace('"', "'")
            lines.append(f'- [{old_idx}] {etype} "{name}" removed')

        if len(lines) == 2:
            lines.append("(no visible changes)")

        self.prev_elements = indexed
        return "\n".join(lines), indexed

    def _index_elements(self, elements: Iterable[dict]) -> Dict[int, dict]:
        indexed: Dict[int, dict] = {}
        for i, el in enumerate(elements, 1):
            indexed[i] = {
                "name": el.get("name", ""),
                "type": el.get("type", ""),
                "x": int(el.get("x", 0)),
                "y": int(el.get("y", 0)),
            }
        return indexed

    @staticmethod
    def _signature(el: dict) -> str:
        return f"{el.get('type','')}|{el.get('name','')}|{el.get('x',0)}|{el.get('y',0)}"

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
        }
        return mapping.get(control_type, "el")
