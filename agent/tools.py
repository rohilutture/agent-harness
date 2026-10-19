"""Toolbox: native Python tools and MCP-served tools behind one interface.

Every call is validated against the tool's JSON schema before running, outputs
are truncated to a budget, and every failure (bad args, unknown tool, exception,
MCP error) becomes a tool *result* the model can read and recover from. The loop
never crashes because a model produced a malformed call.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .mcp import MCPClient
from .memory import NoteStore

_TYPES = {"string": str, "integer": int, "number": (int, float), "boolean": bool,
          "object": dict, "array": list}


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict
    fn: Callable[..., str]

    def spec(self):
        return {"name": self.name, "description": self.description, "input_schema": self.input_schema}


def validate(schema: dict, args: dict) -> str | None:
    if "_raw" in args:
        return f"arguments were not valid JSON: {args['_raw']!r}"
    props = schema.get("properties", {})
    for r in schema.get("required", []):
        if r not in args:
            return f"missing required argument '{r}'"
    for k, v in args.items():
        if k not in props:
            return f"unknown argument '{k}'; expected one of {sorted(props)}"
        t = props[k].get("type")
        if t in _TYPES and not isinstance(v, _TYPES[t]):
            return f"argument '{k}' should be {t}, got {type(v).__name__}"
    return None


class Toolbox:
    def __init__(self, max_output_chars: int = 4000):
        self.tools: dict[str, Tool] = {}
        self.max_chars = max_output_chars
        self.clients: list[MCPClient] = []

    def add(self, tool: Tool):
        self.tools[tool.name] = tool

    def add_mcp(self, client: MCPClient, prefix: str = ""):
        self.clients.append(client)
        for t in client.list_tools():
            name = prefix + t["name"]
            self.add(Tool(name, t.get("description", ""), t.get("inputSchema", {"type": "object"}),
                          (lambda n: lambda **kw: client.call_tool(n, kw))(t["name"])))

    def add_memory(self, store: NoteStore):
        self.add(Tool("write_note", "Save a durable note (e.g. a user preference or an intermediate "
                      "result) under a short key. Notes persist across sessions.",
                      {"type": "object", "properties": {"key": {"type": "string"},
                                                        "content": {"type": "string"}},
                       "required": ["key", "content"]}, store.write))
        self.add(Tool("search_notes", "Search your saved notes by keywords.",
                      {"type": "object", "properties": {"query": {"type": "string"}},
                       "required": ["query"]}, store.search))

    def specs(self) -> list[dict]:
        return [t.spec() for t in self.tools.values()]

    def call(self, name: str, args: dict) -> tuple[str, bool]:
        tool = self.tools.get(name)
        if tool is None:
            return f"ERROR: unknown tool '{name}'. Available: {sorted(self.tools)}", True
        err = validate(tool.input_schema, args)
        if err:
            return f"ERROR: {err}", True
        try:
            out = tool.fn(**args)
            text, is_err = out if isinstance(out, tuple) else (str(out), False)
        except Exception as e:
            text, is_err = f"ERROR: {type(e).__name__}: {e}", True
        if len(text) > self.max_chars:
            text = text[:self.max_chars] + f"\n... [truncated {len(text) - self.max_chars} chars]"
        return (("ERROR: " + text) if is_err and not text.startswith("ERROR") else text), is_err

    def close(self):
        for c in self.clients:
            c.close()
