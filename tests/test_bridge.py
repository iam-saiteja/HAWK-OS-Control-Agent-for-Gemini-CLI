from hawk.bridge import Bridge


def test_format_snapshot() -> None:
    bridge = Bridge()
    snapshot = bridge.format_snapshot(
        [
            {"name": "File", "type": "MenuBarControl", "x": 30, "y": 20},
            {"name": "Save", "type": "ButtonControl", "x": 100, "y": 400},
        ],
        "Notepad",
    )

    assert "WINDOW: Notepad" in snapshot
    assert "[2] btn \"Save\" (100,400)" in snapshot
    assert bridge.get_elements()[1]["name"] == "File"


def test_format_diff_added_removed() -> None:
    bridge = Bridge()
    bridge.format_snapshot([{"name": "Run", "type": "ButtonControl", "x": 50, "y": 30}], "Editor")

    diff = bridge.format_diff(
        [{"name": "Save", "type": "ButtonControl", "x": 80, "y": 30}],
        "Editor",
    )

    assert "DIFF:" in diff
    assert "+ [2] btn \"Save\" (80,30)" in diff
    assert "- [1] \"Run\" removed" in diff


def test_format_diff_bucket_stability() -> None:
    bridge = Bridge()
    bridge.format_snapshot(
        [{"name": "Search", "type": "ButtonControl", "x": 40, "y": 40}],
        "Editor",
    )

    diff = bridge.format_diff(
        [{"name": "Search", "type": "ButtonControl", "x": 95, "y": 90}],
        "Editor",
    )

    assert diff == "DIFF: no changes"


def test_format_snapshot_caps_elements_to_30() -> None:
    bridge = Bridge()
    elements = [
        {"name": f"Item {i}", "type": "ButtonControl", "x": i, "y": i}
        for i in range(1, 45)
    ]

    snapshot = bridge.format_snapshot(elements, "Overflow Window")

    assert "[30] btn \"Item 30\" (30,30)" in snapshot
    assert "Item 31" not in snapshot
    assert len(bridge.get_elements()) == 30


def test_format_diff_caps_new_elements_to_30() -> None:
    bridge = Bridge()
    initial = [
        {"name": f"Old {i}", "type": "ButtonControl", "x": i, "y": i}
        for i in range(1, 10)
    ]
    bridge.format_snapshot(initial, "Editor")

    incoming = [
        {"name": f"New {i}", "type": "ButtonControl", "x": i * 10, "y": i * 10}
        for i in range(1, 50)
    ]
    diff = bridge.format_diff(incoming, "Editor")

    assert "New 30" in diff
    assert "New 31" not in diff
