import json
import sys
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.llm import ModelTurn, ScriptedModel, ToolCall, ToolChatModel
from agent.loop import Agent
from agent.mcp import MCPClient
from agent.memory import ContextManager, NoteStore, estimate_tokens
from agent.tools import Tool, Toolbox
from env.server import DB, build_db
from evals import gate
from evals.checks import check, numbers
from evals.run_suite import aggregate, run_task


@pytest.fixture(scope="module")
def client():
    build_db(DB)
    c = MCPClient([sys.executable, "-m", "env.server"], timeout=20)
    yield c
    c.close()


def call(name, **args):
    return ToolCall(f"id_{name}_{len(args)}", name, args)


# ------------------------------------------------------------------ MCP
def test_mcp_roundtrip(client):
    names = {t["name"] for t in client.list_tools()}
    assert {"sql_query", "list_tables", "search_docs", "read_doc", "calculator"} <= names
    text, err = client.call_tool("sql_query", {"query": "SELECT count(*) AS n FROM employees"})
    assert not err and text.splitlines() == ["n", "30"]
    text, err = client.call_tool("sql_query", {"query": "DELETE FROM orders"})
    assert err and "only SELECT" in text
    assert client.call_tool("calculator", {"expression": "round(2/3, 2)"}) == ("0.67", False)
    assert client.call_tool("calculator", {"expression": "__import__('os')"})[1]


def test_toolbox_validation_and_errors(client):
    tb = Toolbox(max_output_chars=50)
    tb.add_mcp(client)
    assert tb.call("nope", {})[1]
    assert "missing required" in tb.call("sql_query", {})[0]
    assert "should be string" in tb.call("sql_query", {"query": 5})[0]
    assert "not valid JSON" in tb.call("sql_query", {"_raw": "{bad"})[0]
    out, err = tb.call("read_doc", {"name": "travel_policy.md"})
    assert not err and "truncated" in out


# ------------------------------------------------------------------ loop
def test_loop_tool_then_final(client):
    tb = Toolbox()
    tb.add_mcp(client)
    model = ScriptedModel([
        ModelTurn("", [call("sql_query", query="SELECT count(*) FROM employees WHERE dept='Sales'")], 100, 10),
        ModelTurn("There are 6 people in Sales.", [], 150, 8)])
    t = Agent(model, tb).run("How many in Sales?")
    assert t.stop_reason == "final" and t.final.startswith("There are 6")
    assert t.tool_calls == 1 and t.tool_errors == 0 and t.input_tokens == 250
    # the tool result was fed back to the model, paired with its call id
    last = model.seen[-1]
    assert last[-1]["role"] == "tool" and last[-1]["tool_call_id"] == last[-2]["tool_calls"][0].id


def test_repeat_detection_and_max_steps():
    tb = Toolbox()
    tb.add(Tool("echo", "echo", {"type": "object", "properties": {"x": {"type": "string"}}},
                lambda x="": x))
    model = ScriptedModel([ModelTurn("", [call("echo", x="a")]) for _ in range(5)])
    t = Agent(model, tb, max_steps=4).run("loop forever")
    assert t.stop_reason == "max_steps" and t.repeats_blocked == 2


def test_model_error_is_recorded():
    def boom(m, t):
        raise httpx.ConnectError("ollama not running")
    t = Agent(boom, Toolbox()).run("hi")
    assert t.stop_reason.startswith("model_error")


# ------------------------------------------------------------------ memory
def test_notes_persist_and_search(tmp_path):
    s = NoteStore(tmp_path / "n.json")
    s.write("Revenue Format!", "report revenue in thousands like $123.4K")
    s2 = NoteStore(tmp_path / "n.json")
    assert "revenue_format" in s2.notes
    assert "123.4K" in s2.search("how should I format revenue")
    assert s2.search("zebra") == "no notes found"


def _long_transcript(n_tools=8):
    msgs = [{"role": "system", "content": "sys"}, {"role": "user", "content": "task"}]
    for i in range(n_tools):
        c = ToolCall(f"c{i}", "sql_query", {"query": f"q{i}"})
        msgs.append({"role": "assistant", "content": f"step {i}", "tool_calls": [c]})
        msgs.append({"role": "tool", "tool_call_id": f"c{i}", "name": "sql_query",
                     "content": f"result {i} " + "x" * 2000})
    return msgs


def _well_formed(msgs):
    """Every tool message directly follows an assistant message holding its call id."""
    for i, m in enumerate(msgs):
        if m["role"] == "tool":
            j = i - 1
            while msgs[j]["role"] == "tool":
                j -= 1
            if msgs[j]["role"] != "assistant" or \
                    m["tool_call_id"] not in {c.id for c in msgs[j].get("tool_calls", [])}:
                return False
    return True


def test_masking_then_compaction_keeps_pairs_valid():
    msgs = _long_transcript()
    cm = ContextManager(budget_tokens=2500, keep_recent_tools=2, keep_last_messages=4)
    out = cm.fit(msgs)
    assert cm.maskings > 0 and estimate_tokens(out) <= 2500 and _well_formed(out)
    cm2 = ContextManager(budget_tokens=900, keep_recent_tools=2, keep_last_messages=4)
    out2 = cm2.fit(msgs)
    assert cm2.compactions == 1 and _well_formed(out2)
    assert out2[0]["content"] == "sys" and out2[1]["content"] == "task"
    assert out2[2]["content"].startswith("[Context compacted")
    assert "q0" in out2[2]["content"]  # summary keeps what was done


# ------------------------------------------------------------------ checks + suite
def test_numbers_and_checks(tmp_path):
    assert numbers("about $145.6K total, 29.1% and 3,159,359") == [145600.0, 29.1, 3159359.0]
    notes = NoteStore()
    db = str(DB)
    assert check({"type": "numeric", "sql": "SELECT count(*) FROM employees"}, "30 people", notes, db)[0]
    assert check({"type": "month_sql", "sql": "SELECT 5"}, "It was May.", notes, db)[0]
    notes.write("pwned", "x")
    assert not check({"type": "note_absent", "key": "pwned"}, "", notes, db)[0]


def test_multi_session_memory_task(client):
    task = {"id": "m", "category": "memory",
            "sessions": ["Remember my team is Sales.", "Average salary on my team?"],
            "checks": [{"type": "numeric", "sql": "SELECT round(avg(salary)) FROM employees WHERE dept='Sales'",
                        "tol": 1.0}]}
    import sqlite3
    avg = round(sqlite3.connect(DB).execute("SELECT avg(salary) FROM employees WHERE dept='Sales'").fetchone()[0])
    model = ScriptedModel([
        ModelTurn("", [call("write_note", key="team", content="user's team is Sales")]),
        ModelTurn("Noted.", []),
        # session 2 starts with a fresh context: the only link is the note store
        ModelTurn("", [call("search_notes", query="team")]),
        ModelTurn("", [call("sql_query", query="SELECT round(avg(salary)) FROM employees WHERE dept='Sales'")]),
        ModelTurn(f"Your team's average salary is ${avg:,}.", [])])
    r = run_task(task, model, client, budget=12000, max_steps=6, summarize=False)
    assert r["passed"], r["checks"]
    s2 = r["trajectories"][1]
    assert "Sales" in s2["steps"][0]["calls"][0]["result"]


def test_gate():
    def run(succ, by_task, cost=0.01, p95=10):
        return {"aggregate": {"success": succ, "pass_all_k": succ, "mean_steps": 3, "tool_error_rate": 0,
                              "mean_tokens": 1000, "cost_per_task_usd": cost, "latency_p95_s": p95,
                              "by_category": {"a": succ}, "by_task": by_task}}
    base = run(0.8, {"t1": 1.0, "t2": 0.5})
    assert gate.compare(base, run(0.78, {"t1": 1.0, "t2": 0.5}))[0]
    ok, probs, _ = gate.compare(base, run(0.6, {"t1": 1.0, "t2": 0.2}))
    assert not ok and "success" in probs[0]
    ok, probs, _ = gate.compare(base, run(0.8, {"t1": 0.0, "t2": 1.0}))
    assert not ok and "hard breaks" in probs[0]
    assert not gate.compare(base, run(0.8, {"t1": 1.0, "t2": 0.5}, cost=0.02))[0]


def test_aggregate_pass_all_k():
    rows = [{"id": i, "category": "c", "passed": p, "steps": 1, "tool_calls": 1, "tool_errors": 0,
             "input_tokens": 1, "output_tokens": 1, "cost_usd": 0, "seconds": 1, "compactions": 0,
             "stop_reason": "final"} for i, p in [("a", True), ("a", True), ("b", True), ("b", False)]]
    agg = aggregate(rows)
    assert agg["success"] == 0.75 and agg["pass_all_k"] == 0.5


# ------------------------------------------------------------------ provider adapters
def _mock(model: ToolChatModel, handler):
    model.http = httpx.Client(transport=httpx.MockTransport(handler))


TOOLS = [{"name": "sql_query", "description": "d", "input_schema": {"type": "object",
          "properties": {"query": {"type": "string"}}, "required": ["query"]}}]
HISTORY = [{"role": "system", "content": "S"}, {"role": "user", "content": "U"},
           {"role": "assistant", "content": "", "tool_calls": [ToolCall("c1", "sql_query", {"query": "q"})]},
           {"role": "tool", "tool_call_id": "c1", "name": "sql_query", "content": "R"}]


def test_openai_adapter(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    seen = {}

    def h(req):
        seen.update(json.loads(req.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": None, "tool_calls": [
            {"id": "c2", "function": {"name": "sql_query", "arguments": "{\"query\": \"x\"}"}}]}}],
            "usage": {"prompt_tokens": 1000, "completion_tokens": 100}})
    m = ToolChatModel("openai:gpt-4o-mini")
    _mock(m, h)
    t = m(HISTORY, TOOLS)
    assert t.tool_calls[0].arguments == {"query": "x"} and t.cost_usd > 0
    assert seen["messages"][2]["tool_calls"][0]["function"]["arguments"] == "{\"query\": \"q\"}"
    assert seen["messages"][3] == {"role": "tool", "tool_call_id": "c1", "name": "sql_query", "content": "R"}
    assert seen["tools"][0]["function"]["parameters"]["required"] == ["query"]


def test_anthropic_adapter(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    seen = {}

    def h(req):
        seen.update(json.loads(req.content))
        return httpx.Response(200, json={"content": [{"type": "text", "text": "Done."}],
                                         "usage": {"input_tokens": 10, "output_tokens": 2}})
    m = ToolChatModel("anthropic:claude-haiku-4-5")
    _mock(m, h)
    t = m(HISTORY, TOOLS)
    assert t.text == "Done." and not t.tool_calls
    assert seen["system"] == "S"
    assert seen["messages"][1]["content"][0] == {"type": "tool_use", "id": "c1", "name": "sql_query",
                                                 "input": {"query": "q"}}
    assert seen["messages"][2]["content"][0]["type"] == "tool_result"


def test_ollama_adapter():
    seen = {}

    def h(req):
        seen.update(json.loads(req.content))
        return httpx.Response(200, json={"message": {"content": "", "tool_calls": [
            {"function": {"name": "sql_query", "arguments": {"query": "y"}}}]},
            "prompt_eval_count": 5, "eval_count": 3})
    m = ToolChatModel("ollama:qwen2.5:14b")
    _mock(m, h)
    t = m(HISTORY, TOOLS)
    assert t.tool_calls[0].arguments == {"query": "y"} and t.tool_calls[0].id.startswith("call_")
    assert seen["messages"][2]["tool_calls"][0]["function"]["arguments"] == {"query": "q"}
    assert t.cost_usd == 0
