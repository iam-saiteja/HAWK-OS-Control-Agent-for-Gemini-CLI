import hawk.agent as agent_module
from hawk.agent import (
    _extract_action,
    _extract_message_content,
    _extract_message_target,
    _extract_search_query,
    _extract_site_search,
    _normalize_debug_reply,
    _normalize_task_text,
    _plan_post_launch_actions,
    _plan_whatsapp_post_launch_actions,
    _should_plan_browser_search,
    _should_plan_whatsapp_message,
    _trim_chat_history,
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


def test_extract_action_with_markdown_noise() -> None:
    reply = """```\n- **click [9]**\n```"""
    assert _extract_action(reply) == "click 9"


def test_normalize_debug_reply_unescapes_newlines() -> None:
    reply = "\\nlaunch whatsapp\\nclick 1"
    assert _normalize_debug_reply(reply) == "\nlaunch whatsapp\nclick 1"


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


def test_extract_message_target() -> None:
    task = "open whatsapp application and send message to side chick contact, message content(hello)"
    assert _extract_message_target(task) == "side chick"


def test_extract_message_target_from_search_contact_pattern() -> None:
    task = "open whatsapp and search fro contact (BHD)and text BHD contact hiii"
    assert _extract_message_target(task) == "BHD"


def test_extract_message_content() -> None:
    task = "open whatsapp application and send message to side chick contact, message content(hello)"
    assert _extract_message_content(task) == "hello"


def test_extract_message_content_from_text_contact_pattern() -> None:
    task = "open whatsapp and search fro contact (BHD)and text BHD contact hiii"
    assert _extract_message_content(task) == "hiii"


def test_should_plan_whatsapp_message() -> None:
    task = "open whatsapp application and send message to side chick contact, message content(hello)"
    assert _should_plan_whatsapp_message(task, "launch whatsapp") is True


def test_plan_whatsapp_post_launch_actions() -> None:
    task = "open whatsapp application and send message to side chick contact, message content(hello)"
    assert _plan_whatsapp_post_launch_actions(task) == [
        "key ctrl+f",
        "type 0 side chick",
        "key enter",
        "type 0 hello",
        "key enter",
    ]


def test_trim_chat_history_keeps_system_plus_last_six_turns() -> None:
    agent_module._chat_history = []
    agent_module._chat_history.append({"role": "system", "content": "sys"})
    for i in range(10):
        agent_module._chat_history.append({"role": "user", "content": f"u{i}"})
        agent_module._chat_history.append({"role": "assistant", "content": f"a{i}"})

    _trim_chat_history()

    assert len(agent_module._chat_history) == 13
    assert agent_module._chat_history[0]["role"] == "system"
    assert agent_module._chat_history[1]["content"] == "u4"
    assert agent_module._chat_history[-1]["content"] == "a9"

    agent_module.reset_chat()
