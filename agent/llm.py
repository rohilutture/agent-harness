"""Tool-calling chat over plain HTTP for Ollama, OpenAI and Anthropic.

The agent loop speaks one neutral message format; each provider adapter
translates to and from its own wire format. Neutral messages:
  {"role": "system"|"user"|"assistant"|"tool", "content": str,
   "tool_calls": [ToolCall, ...]        (assistant only)
   "tool_call_id": str, "name": str}    (tool only)
"""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field

import httpx

PRICES = {  # USD per 1M tokens (in, out). Update to current list prices.
    "openai:gpt-4o-mini": (0.15, 0.60),
    "openai:gpt-4.1-mini": (0.40, 1.60),
    "anthropic:claude-haiku-4-5": (1.00, 5.00),
}


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class ModelTurn:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    seconds: float = 0.0
    cost_usd: float = 0.0


def _args(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    try:
        v = json.loads(raw or "{}")
        return v if isinstance(v, dict) else {"_raw": raw}
    except json.JSONDecodeError:
        return {"_raw": raw}  # surfaced to the model as a tool error, not a crash


class ToolChatModel:
    def __init__(self, spec: str, temperature: float = 0.0, max_tokens: int = 1024,
                 timeout: float = 180):
        self.spec = spec
        self.provider, self.model = spec.split(":", 1)
        self.temperature, self.max_tokens = temperature, max_tokens
        self.http = httpx.Client(timeout=timeout)

    def __call__(self, messages: list[dict], tools: list[dict]) -> ModelTurn:
        t0 = time.perf_counter()
        turn = getattr(self, f"_{self.provider}")(messages, tools)
        turn.seconds = time.perf_counter() - t0
        pin, pout = PRICES.get(self.spec, (0.0, 0.0))
        turn.cost_usd = (turn.input_tokens * pin + turn.output_tokens * pout) / 1e6
        return turn

    # ------------------------------------------------------------- OpenAI-style
    @staticmethod
    def _oa_messages(messages, args_as_str=True):
        out = []
        for m in messages:
            if m["role"] == "assistant" and m.get("tool_calls"):
                out.append({"role": "assistant", "content": m.get("content") or "",
                            "tool_calls": [{"id": c.id, "type": "function", "function": {
                                "name": c.name,
                                "arguments": json.dumps(c.arguments) if args_as_str else c.arguments}}
                                for c in m["tool_calls"]]})
            elif m["role"] == "tool":
                out.append({"role": "tool", "tool_call_id": m["tool_call_id"],
                            "name": m["name"], "content": m["content"]})
            else:
                out.append({"role": m["role"], "content": m["content"]})
        return out

    @staticmethod
    def _oa_tools(tools):
        return [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                                  "parameters": t["input_schema"]}} for t in tools]

    def _openai(self, messages, tools):
        r = self.http.post("https://api.openai.com/v1/chat/completions",
                           headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
                           json={"model": self.model, "temperature": self.temperature,
                                 "max_tokens": self.max_tokens,
                                 "messages": self._oa_messages(messages),
                                 **({"tools": self._oa_tools(tools)} if tools else {})})
        r.raise_for_status()
        j = r.json()
        msg = j["choices"][0]["message"]
        calls = [ToolCall(c["id"], c["function"]["name"], _args(c["function"]["arguments"]))
                 for c in msg.get("tool_calls") or []]
        return ModelTurn(msg.get("content") or "", calls, j["usage"]["prompt_tokens"],
                         j["usage"]["completion_tokens"])

    def _ollama(self, messages, tools):
        host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        r = self.http.post(f"{host}/api/chat", json={
            "model": self.model, "stream": False,
            "options": {"temperature": self.temperature, "num_predict": self.max_tokens,
                        "num_ctx": int(os.environ.get("OLLAMA_NUM_CTX", 16384))},
            "messages": self._oa_messages(messages, args_as_str=False),
            **({"tools": self._oa_tools(tools)} if tools else {})})
        r.raise_for_status()
        j = r.json()
        msg = j["message"]
        calls = [ToolCall(f"call_{uuid.uuid4().hex[:8]}", c["function"]["name"],
                          _args(c["function"].get("arguments")))
                 for c in msg.get("tool_calls") or []]
        return ModelTurn(msg.get("content") or "", calls, j.get("prompt_eval_count", 0),
                         j.get("eval_count", 0))

    # ---------------------------------------------------------------- Anthropic
    def _anthropic(self, messages, tools):
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        conv = []
        for m in messages:
            if m["role"] == "system":
                continue
            if m["role"] == "assistant":
                blocks = ([{"type": "text", "text": m["content"]}] if m.get("content") else [])
                blocks += [{"type": "tool_use", "id": c.id, "name": c.name, "input": c.arguments}
                           for c in m.get("tool_calls") or []]
                conv.append({"role": "assistant", "content": blocks or [{"type": "text", "text": "."}]})
            elif m["role"] == "tool":
                block = {"type": "tool_result", "tool_use_id": m["tool_call_id"], "content": m["content"]}
                if conv and conv[-1]["role"] == "user" and isinstance(conv[-1]["content"], list):
                    conv[-1]["content"].append(block)  # parallel results share one user turn
                else:
                    conv.append({"role": "user", "content": [block]})
            else:
                conv.append({"role": "user", "content": m["content"]})
        r = self.http.post("https://api.anthropic.com/v1/messages",
                           headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"],
                                    "anthropic-version": "2023-06-01"},
                           json={"model": self.model, "max_tokens": self.max_tokens,
                                 "temperature": self.temperature, "system": system,
                                 "messages": conv,
                                 "tools": [{"name": t["name"], "description": t["description"],
                                            "input_schema": t["input_schema"]} for t in tools]})
        r.raise_for_status()
        j = r.json()
        text = "".join(b["text"] for b in j["content"] if b["type"] == "text")
        calls = [ToolCall(b["id"], b["name"], b["input"]) for b in j["content"] if b["type"] == "tool_use"]
        return ModelTurn(text, calls, j["usage"]["input_tokens"], j["usage"]["output_tokens"])


class ScriptedModel:
    """Replays a fixed list of turns. For tests and for deterministic harness checks."""

    def __init__(self, turns: list[ModelTurn]):
        self.turns = list(turns)
        self.seen: list[list[dict]] = []

    def __call__(self, messages, tools):
        self.seen.append([dict(m) for m in messages])
        if not self.turns:
            return ModelTurn("(script exhausted)")
        return self.turns.pop(0)
