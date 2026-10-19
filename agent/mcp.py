"""A minimal Model Context Protocol (MCP) client and server over stdio.

MCP is JSON-RPC 2.0. On the stdio transport each message is one line of JSON.
The subset implemented here is what tool use needs:
  initialize -> notifications/initialized -> tools/list -> tools/call
That subset is enough to talk to real MCP servers too (e.g. a FastMCP server),
which is the point: the agent's tools come from a protocol, not from imports.
"""
from __future__ import annotations

import itertools
import json
import subprocess
import sys
import threading
from typing import Callable

PROTOCOL_VERSION = "2025-06-18"


class MCPError(RuntimeError):
    pass


class MCPClient:
    """One background thread reads stdout and routes each response to the waiting
    request by id, so a slow or timed-out call can never steal another's reply."""

    def __init__(self, command: list[str], timeout: float = 30.0, env=None, cwd=None):
        self.proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, text=True, bufsize=1, env=env,
                                     cwd=cwd)
        self.timeout = timeout
        self._ids = itertools.count(1)
        self._write = threading.Lock()
        self._pending: dict[int, dict] = {}
        self._events: dict[int, threading.Event] = {}
        threading.Thread(target=self._reader, daemon=True).start()
        self.server_info = self._request("initialize", {
            "protocolVersion": PROTOCOL_VERSION, "capabilities": {},
            "clientInfo": {"name": "agent-harness", "version": "0.1"}})
        self._notify("notifications/initialized")

    def _reader(self):
        for line in self.proc.stdout:
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue  # servers sometimes print logs to stdout; ignore them
            rid = msg.get("id")
            if rid in self._events:
                self._pending[rid] = msg
                self._events[rid].set()

    def _send(self, msg: dict):
        with self._write:
            self.proc.stdin.write(json.dumps(msg) + "\n")
            self.proc.stdin.flush()

    def _notify(self, method, params=None):
        self._send({"jsonrpc": "2.0", "method": method, **({"params": params} if params else {})})

    def _request(self, method, params=None):
        rid = next(self._ids)
        ev = self._events[rid] = threading.Event()
        self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}})
        if not ev.wait(self.timeout):
            self._events.pop(rid, None)
            raise MCPError(f"timeout waiting for {method}")
        msg = self._pending.pop(rid)
        self._events.pop(rid, None)
        if "error" in msg:
            raise MCPError(msg["error"].get("message", str(msg["error"])))
        return msg["result"]

    def list_tools(self) -> list[dict]:
        return self._request("tools/list")["tools"]

    def call_tool(self, name: str, arguments: dict) -> tuple[str, bool]:
        res = self._request("tools/call", {"name": name, "arguments": arguments})
        text = "\n".join(c.get("text", "") for c in res.get("content", []) if c.get("type") == "text")
        return text, bool(res.get("isError"))

    def close(self):
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()


class MCPServer:
    """Register plain functions with a JSON schema; serve them over stdio."""

    def __init__(self, name: str):
        self.name = name
        self.tools: dict[str, tuple[dict, Callable]] = {}

    def tool(self, name: str, description: str, schema: dict):
        def deco(fn):
            self.tools[name] = ({"name": name, "description": description, "inputSchema": schema}, fn)
            return fn
        return deco

    def handle(self, msg: dict) -> dict | None:
        method, rid = msg.get("method"), msg.get("id")
        if rid is None:
            return None  # notification
        try:
            if method == "initialize":
                result = {"protocolVersion": PROTOCOL_VERSION, "capabilities": {"tools": {}},
                          "serverInfo": {"name": self.name, "version": "0.1"}}
            elif method == "tools/list":
                result = {"tools": [spec for spec, _ in self.tools.values()]}
            elif method == "tools/call":
                name, args = msg["params"]["name"], msg["params"].get("arguments", {})
                if name not in self.tools:
                    raise KeyError(f"unknown tool {name}")
                try:
                    out = self.tools[name][1](**args)
                    result = {"content": [{"type": "text", "text": str(out)}], "isError": False}
                except Exception as e:  # tool errors go back to the model, not up the stack
                    result = {"content": [{"type": "text", "text": f"{type(e).__name__}: {e}"}],
                              "isError": True}
            elif method == "ping":
                result = {}
            else:
                return {"jsonrpc": "2.0", "id": rid,
                        "error": {"code": -32601, "message": f"method not found: {method}"}}
            return {"jsonrpc": "2.0", "id": rid, "result": result}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32603, "message": str(e)}}

    def serve_stdio(self):
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            resp = self.handle(json.loads(line))
            if resp is not None:
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()
