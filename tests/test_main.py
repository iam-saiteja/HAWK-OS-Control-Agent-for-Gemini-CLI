import hawk.main as main_module


def test_run_adds_extra_wait_after_launch(monkeypatch) -> None:
    sleeps: list[float] = []

    monkeypatch.setattr(main_module, "reset_chat", lambda: None)

    actions = iter(["launch whatsapp", "done"])
    monkeypatch.setattr(main_module, "ask_agent", lambda snapshot, task: next(actions))
    monkeypatch.setattr(main_module, "verify_progress", lambda task, history, snapshot: "CONTINUE")

    monkeypatch.setattr(
        main_module,
        "get_screen_state",
        lambda: ("Window", [{"name": "Input", "type": "EditControl", "x": 100, "y": 200}]),
    )

    monkeypatch.setattr(
        main_module,
        "execute_action",
        lambda action, elements: action != "done",
    )

    monkeypatch.setattr(main_module.time, "sleep", lambda value: sleeps.append(value))

    main_module.run("open whatsapp", max_turns=5, settle_seconds=0.1)

    assert 2.5 in sleeps


def test_should_use_blind_bootstrap_for_open_on_first_turn() -> None:
    assert main_module._should_use_blind_bootstrap("open whatsapp", 0) is True


def test_should_use_blind_bootstrap_false_on_later_turns() -> None:
    assert main_module._should_use_blind_bootstrap("open whatsapp", 1) is False


def test_should_use_blind_bootstrap_false_for_non_launch_task() -> None:
    assert main_module._should_use_blind_bootstrap("type hello", 0) is False
