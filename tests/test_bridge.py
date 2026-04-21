from hawk.bridge import Bridge


def test_format_snapshot() -> None:
    bridge = Bridge()
    snapshot, indexed = bridge.format_snapshot(
        [
            {"name": "File", "type": "MenuBarControl", "x": 30, "y": 20},
            {"name": "Save", "type": "ButtonControl", "x": 100, "y": 400},
        ],
        "Notepad",
    )

    assert "WINDOW: Notepad" in snapshot
    assert "[2] btn \"Save\" (100,400)" in snapshot
    assert indexed[1]["name"] == "File"


def test_format_diff() -> None:
    bridge = Bridge()
    bridge.format_snapshot([{"name": "Run", "type": "ButtonControl", "x": 50, "y": 30}], "Editor")

    diff, _ = bridge.format_diff(
        [{"name": "Save", "type": "ButtonControl", "x": 80, "y": 30}],
        "Editor",
    )

    assert "DIFF:" in diff
    assert "+ [1] btn \"Save\"" in diff
    assert "removed" in diff
