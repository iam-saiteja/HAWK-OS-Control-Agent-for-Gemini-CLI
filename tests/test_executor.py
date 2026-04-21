from hawk.executor import execute_action


def test_execute_action_done() -> None:
    assert execute_action("done", {}) is False


def test_execute_action_unknown_keeps_loop() -> None:
    assert execute_action("noop", {}) is True
