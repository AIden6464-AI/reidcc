"""
Behavior contract for claude_optimizer_addon.optimize_payload().

The contract cases pass enable_pruning explicitly; the default (False) has
its own test at the bottom.
"""
import copy

import pytest

import claude_optimizer_addon

REMINDER = "<system-reminder>\nfile changed\n</system-reminder>"
DATE = "Today's date is 2026-11-01."
BILLING = "x-anthropic-billing-header: cc_version=1.0"


@pytest.fixture
def optimize():
    return claude_optimizer_addon.optimize_payload


def text(t):
    return {"type": "text", "text": t}


def tool_result(tid, content="ok"):
    return {"type": "tool_result", "tool_use_id": tid, "content": content}


# ---------- contract ----------

@pytest.mark.parametrize("payload", [None, "str", 42, ["messages"]])
def test_non_dict_returned_unchanged(optimize, payload):
    assert optimize(payload, enable_pruning=False) == payload


def test_dict_without_messages_returned_unchanged(optimize):
    payload = {"system": DATE, "tools": [{"name": "PowerShell"}]}
    snapshot = copy.deepcopy(payload)
    assert optimize(payload, enable_pruning=True) == snapshot


def test_clean_payload_is_untouched(optimize):
    payload = {
        "system": [text("You are Claude.")],
        "messages": [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": [text("hello")]},
            {"role": "user", "content": [text("do X")]},
        ],
    }
    snapshot = copy.deepcopy(payload)
    assert optimize(payload, enable_pruning=False) == snapshot


def test_string_system_normalized_to_block_list(optimize):
    payload = {"system": "You are Claude.", "messages": [{"role": "user", "content": "hi"}]}
    out = optimize(payload, enable_pruning=False)
    assert out["system"] == [text("You are Claude.")]
    assert out["messages"] == [{"role": "user", "content": "hi"}]


def test_date_hoisted_from_string_system_into_final_message(optimize):
    payload = {"system": DATE, "messages": [{"role": "user", "content": "hi"}]}
    out = optimize(payload, enable_pruning=False)
    assert out["system"] == []
    assert out["messages"][-1]["content"] == f"{DATE}\n\nhi"


def test_billing_and_date_blocks_hoisted_static_blocks_kept(optimize):
    payload = {
        "system": [text(BILLING), text("You are Claude."), text(DATE)],
        "messages": [{"role": "user", "content": [text("go")]}],
    }
    out = optimize(payload, enable_pruning=False)
    assert out["system"] == [text("You are Claude.")]
    assert out["messages"][-1]["content"] == [text(f"{BILLING}\n\n{DATE}"), text("go")]


def test_midconversation_reminder_block_moved_to_final_message(optimize):
    payload = {
        "messages": [
            {"role": "user", "content": [text("first"), text(REMINDER)]},
            {"role": "assistant", "content": [text("ack")]},
            {"role": "user", "content": [text("second")]},
        ]
    }
    out = optimize(payload, enable_pruning=False)
    assert out["messages"][0]["content"] == [text("first")]
    assert out["messages"][-1]["content"] == [text(REMINDER), text("second")]


def test_midconversation_string_reminder_message_dropped_and_hoisted(optimize):
    payload = {
        "messages": [
            {"role": "user", "content": REMINDER},
            {"role": "user", "content": "real question"},
        ]
    }
    out = optimize(payload, enable_pruning=False)
    assert out["messages"] == [{"role": "user", "content": f"{REMINDER}\n\nreal question"}]


def test_midconversation_message_with_only_reminder_blocks_dropped(optimize):
    payload = {
        "messages": [
            {"role": "user", "content": [text(REMINDER)]},
            {"role": "user", "content": [text("q")]},
        ]
    }
    out = optimize(payload, enable_pruning=False)
    assert len(out["messages"]) == 1
    assert out["messages"][0]["content"] == [text(REMINDER), text("q")]


def test_saboteurs_inserted_after_leading_tool_results(optimize):
    payload = {
        "system": [text(DATE)],
        "messages": [
            {"role": "assistant", "content": [{"type": "tool_use", "id": "a", "name": "Read", "input": {}},
                                              {"type": "tool_use", "id": "b", "name": "Read", "input": {}}]},
            {"role": "user", "content": [tool_result("a"), tool_result("b"), text("more")]},
        ],
    }
    out = optimize(payload, enable_pruning=False)
    assert out["messages"][-1]["content"] == [
        tool_result("a"), tool_result("b"), text(DATE), text("more"),
    ]


def test_tool_result_only_final_message_reminder_reinserted_after_results(optimize):
    payload = {
        "messages": [
            {"role": "assistant", "content": [{"type": "tool_use", "id": "a", "name": "Read", "input": {}}]},
            {"role": "user", "content": [tool_result("a"), text(REMINDER)]},
        ]
    }
    out = optimize(payload, enable_pruning=False)
    assert out["messages"][-1]["content"] == [tool_result("a"), text(REMINDER)]


def test_saboteur_order_system_first_then_messages(optimize):
    payload = {
        "system": [text(BILLING)],
        "messages": [
            {"role": "user", "content": [text("<system-reminder>one</system-reminder>")]},
            {"role": "assistant", "content": [text("x")]},
            {"role": "user", "content": [text("<system-reminder>two</system-reminder>"), text("q")]},
        ],
    }
    out = optimize(payload, enable_pruning=False)
    joined = out["messages"][-1]["content"][0]["text"]
    assert joined == "\n\n".join([BILLING, "<system-reminder>one</system-reminder>",
                                  "<system-reminder>two</system-reminder>"])


def test_non_text_blocks_preserved(optimize):
    image = {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "AAAA"}}
    payload = {"messages": [{"role": "user", "content": [image, text(REMINDER), text("what is this")]}]}
    out = optimize(payload, enable_pruning=False)
    assert out["messages"][-1]["content"] == [text(REMINDER), image, text("what is this")]


def test_pruning_enabled_removes_bloat_tools(optimize):
    tools = [
        {"name": "Read"},
        {"name": "PowerShell"},
        {"name": "mcp__claude_ai_Gmail__send"},
        {"name": "Bash"},
        {"name": "CronCreate"},
        {"type": "function", "function": {"name": "NotebookEdit"}},  # OpenAI-shaped
    ]
    payload = {"tools": tools, "messages": [{"role": "user", "content": "hi"}]}
    out = optimize(payload, enable_pruning=True)
    assert out["tools"] == [{"name": "Read"}, {"name": "Bash"}]


def test_pruning_disabled_keeps_all_tools(optimize):
    tools = [{"name": "Read"}, {"name": "PowerShell"}, {"name": "CronCreate"}]
    payload = {"tools": copy.deepcopy(tools), "messages": [{"role": "user", "content": "hi"}]}
    out = optimize(payload, enable_pruning=False)
    assert out["tools"] == tools


@pytest.mark.xfail(strict=True, reason=(
    "KNOWN BUG: a final user message made only of a reminder is dropped and its "
    "text is spliced into the preceding assistant message, so the request ends "
    "on an assistant turn (accidental prefill)."
))
def test_request_still_ends_with_user_turn_when_final_message_is_only_reminder(optimize):
    payload = {
        "messages": [
            {"role": "user", "content": "q"},
            {"role": "assistant", "content": [text("a")]},
            {"role": "user", "content": [text(REMINDER)]},
        ]
    }
    out = optimize(payload, enable_pruning=False)
    assert out["messages"][-1]["role"] == "user"


# ---------- addon specifics ----------

def test_addon_preserves_cache_control():
    payload = {
        "system": [{"type": "text", "text": "static", "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": "q", "cache_control": {"type": "ephemeral"}}]}],
    }
    snapshot = copy.deepcopy(payload)
    assert claude_optimizer_addon.optimize_payload(payload) == snapshot


def test_addon_pruning_off_by_default():
    tools = [{"name": "PowerShell"}, {"name": "Read"}]
    payload = {"tools": copy.deepcopy(tools), "messages": [{"role": "user", "content": "hi"}]}
    assert claude_optimizer_addon.optimize_payload(payload)["tools"] == tools
