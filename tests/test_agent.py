from hawk.agent import (
    _extract_action,
    _extract_search_query,
    _extract_site_search,
    _normalize_task_text,
    _plan_post_launch_actions,
    _should_plan_browser_search,
)


def test_extract_first_valid_action() -> None:
    reply = """I will proceed now
click 3
done"""
    assert _extract_action(reply) == "click 3"


def test_extract_invalid_defaults_done() -> None:
    assert _extract_action("No action provided.") == "done"


def test_extract_type_action() -> None:
    assert _extract_action("type 1 hello world") == "type 1 hello world"


def test_extract_action_does_not_match_embedded_text() -> None:
    assert _extract_action("please click 3 now") == "done"


def test_extract_action_bracketed_click_id() -> None:
    assert _extract_action("click [11]") == "click 11"


def test_extract_search_query() -> None:
    task = "open brave and search for youtube.com"
    assert _extract_search_query(task) == "youtube.com"


def test_should_plan_browser_search() -> None:
    task = "open brave and search for youtube.com"
    assert _should_plan_browser_search(task, "launch brave") is True


def test_plan_post_launch_actions_for_search_task() -> None:
    task = "open brave and search for youtube.com"
    assert _plan_post_launch_actions(task) == [
        "key ctrl+l",
        "type 0 youtube.com",
        "key enter",
    ]


def test_normalize_task_text_common_typos() -> None:
    assert _normalize_task_text("open breave and search for yotube") == "open brave and search for youtube"


def test_extract_site_search_from_multiclause_task() -> None:
    task = "open brave search for youtube.com . in youtube search bixi op"
    assert _extract_site_search(task) == ("youtube", "bixi op")


def test_plan_post_launch_actions_prefers_site_search_url() -> None:
    task = "open brave search for youtube.com . in youtube search bixi op"
    assert _plan_post_launch_actions(task) == [
        "key ctrl+l",
        "type 0 https://www.youtube.com/results?search_query=bixi+op",
        "key enter",
    ]


def test_extract_search_query_truncates_followup_clause() -> None:
    task = "open brave search for youtube.com, in youtube search bixi op"
    assert _extract_search_query(task) == "youtube.com"
