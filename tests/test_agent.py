from hawk.agent import _extract_action


def test_extract_first_valid_action() -> None:
    reply = """I will proceed now
click 3
done"""
    assert _extract_action(reply) == "click 3"


def test_extract_invalid_defaults_done() -> None:
    assert _extract_action("No action provided.") == "done"


def test_extract_type_action() -> None:
    assert _extract_action("type 1 hello world") == "type 1 hello world"
