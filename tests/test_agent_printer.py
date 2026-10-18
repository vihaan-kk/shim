"""Agent loop + fake printer tools, driven by a scripted model (no GPU needed)."""

import json

import pytest

from agent.llm import ScriptedLLM, tool_call
from agent.loop import Agent
from common import confirmations
from common.result import fixable, success
from tools import registry
from tools.fakes import printer_fakes


@pytest.fixture(autouse=True)
def fresh_state():
    registry.load_tools(fake=True)  # imports once; later calls are no-ops
    printer_fakes.reset()
    confirmations.reset()
    yield


def last_tool_result(llm: ScriptedLLM) -> dict:
    """The newest tool result the model saw on its latest call."""
    tool_messages = [m for m in llm.seen[-1] if m["role"] == "tool"]
    return json.loads(tool_messages[-1]["content"])


def test_result_shape():
    r = fixable("out_of_range", "x is 40, max 30", "Use a smaller x.", valid_range={"min": 1, "max": 30})
    assert r.to_dict() == {
        "status": "fixable",
        "data": {},
        "message": "Use a smaller x.",
        "error": {"code": "out_of_range", "reason": "x is 40, max 30", "valid_range": {"min": 1, "max": 30}},
        "retryable": True,
    }
    assert success("ok").to_dict()["error"] is None


def test_bad_enum_is_fixable_then_model_corrects_it():
    llm = ScriptedLLM([
        tool_call("c1", "slice", '{"revision_id": "rev_1", "profile_id": "fast"}'),
        tool_call("c2", "slice", '{"revision_id": "rev_1", "profile_id": "draft_028"}'),
        {"role": "assistant", "content": "Sliced."},
    ])
    pause = Agent(llm).send("slice rev_1")
    assert pause.kind == "answer"
    first = json.loads([m for m in llm.seen[1] if m["role"] == "tool"][0]["content"])
    assert first["status"] == "fixable"
    assert first["error"]["valid_range"] == ["draft_028", "demo_020"]
    assert last_tool_result(llm)["status"] == "success"


def test_slice_refuses_unvalidated_revision():
    llm = ScriptedLLM([
        tool_call("c1", "slice", '{"revision_id": "unvalidated_rev_2", "profile_id": "draft_028"}'),
        {"role": "assistant", "content": "Needs validation first."},
    ])
    Agent(llm).send("slice it")
    assert last_tool_result(llm)["error"]["code"] == "not_validated"


def test_start_print_without_confirmation_is_refused():
    llm = ScriptedLLM([
        tool_call("c1", "slice", '{"revision_id": "rev_1", "profile_id": "draft_028"}'),
    ])
    agent = Agent(llm)
    agent.send("slice")
    job_id = last_tool_result_from(agent)["data"]["job_id"]

    llm.replies = [
        tool_call("c2", "start_print", json.dumps({"job_id": job_id, "confirmation_id": "conf_made_up"})),
        {"role": "assistant", "content": "I need your approval first."},
    ]
    agent.send("print it")
    assert last_tool_result(llm)["error"]["code"] == "confirmation_invalid"


def test_full_print_with_confirmation():
    llm = ScriptedLLM([
        tool_call("c1", "slice", '{"revision_id": "rev_1", "profile_id": "draft_028"}'),
    ])
    agent = Agent(llm)
    agent.send("print rev_1")
    job_id = last_tool_result_from(agent)["data"]["job_id"]

    llm.replies = [
        tool_call("c2", "request_confirmation", json.dumps(
            {"action": "start_print", "subject": job_id, "summary": "Print rev_1, about 42 min."})),
    ]
    pause = agent.send("go ahead")
    assert pause.kind == "confirmation"

    # The confirmation_id is minted by the loop when the person approves.
    llm.replies = [{"role": "assistant", "content": "placeholder"}]
    agent.resolve_confirmation(approved=True)
    confirmation_id = last_tool_result(llm)["data"]["confirmation_id"]

    llm.replies = [
        tool_call("c3", "start_print", json.dumps({"job_id": job_id, "confirmation_id": confirmation_id})),
        tool_call("c4", "start_print", json.dumps({"job_id": job_id, "confirmation_id": confirmation_id})),
        {"role": "assistant", "content": "Started."},
    ]
    agent.send("start")
    tool_results = [json.loads(m["content"]) for m in llm.seen[-1] if m["role"] == "tool"]
    assert tool_results[-2]["status"] == "success"
    assert tool_results[-2]["data"]["verified"] is True
    assert tool_results[-1]["error"]["code"] == "duplicate_start"


def test_ask_user_pauses_and_answer_goes_back_as_tool_result():
    llm = ScriptedLLM([
        tool_call("c1", "ask_user", '{"question": "Which profile, draft or demo?"}'),
        {"role": "assistant", "content": "Thanks."},
    ])
    agent = Agent(llm)
    pause = agent.send("slice it")
    assert pause.kind == "question"
    assert agent.answer_question("draft").kind == "answer"
    assert last_tool_result(llm)["data"]["answer"] == "draft"


def test_retry_limit_turns_repeated_fixable_into_fatal():
    bad = '{"revision_id": "unvalidated_x", "profile_id": "draft_028"}'
    llm = ScriptedLLM([tool_call(f"c{i}", "slice", bad) for i in range(4)] + [
        {"role": "assistant", "content": "Giving up."},
    ])
    Agent(llm, max_fixable_in_a_row=3).send("slice")
    assert last_tool_result(llm)["error"]["code"] == "retry_limit"


def test_step_limit_stops_the_loop():
    llm = ScriptedLLM([tool_call(f"c{i}", "get_printer_status", "{}") for i in range(10)])
    assert Agent(llm, max_steps=5).send("status?").kind == "stopped"


def test_connection_drop_mid_print_is_fatal(monkeypatch):
    monkeypatch.setenv("FAKE_PRINTER_FAULT", "drop")
    job_id = printer_fakes.slice_revision("rev_1", "draft_028").data["job_id"]
    conf = confirmations.create("start_print", job_id, "test")
    assert printer_fakes.start_print(job_id, conf).ok
    assert printer_fakes.get_job_progress(job_id).ok          # 25%
    dropped = printer_fakes.get_job_progress(job_id)            # drop
    assert dropped.status == "fatal" and dropped.error.code == "connection_lost"


def last_tool_result_from(agent: Agent) -> dict:
    tool_messages = [m for m in agent.messages if m["role"] == "tool"]
    return json.loads(tool_messages[-1]["content"])
