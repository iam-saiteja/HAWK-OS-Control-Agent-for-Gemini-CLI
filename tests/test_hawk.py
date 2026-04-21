from hawk.hawk import _dedupe_elements


def test_dedupe_elements() -> None:
    elements = [
        {"name": "A", "type": "ButtonControl", "x": 1, "y": 1},
        {"name": "A", "type": "ButtonControl", "x": 1, "y": 1},
        {"name": "B", "type": "EditControl", "x": 2, "y": 2},
    ]

    deduped = _dedupe_elements(elements)
    assert len(deduped) == 2
