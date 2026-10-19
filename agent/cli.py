"""Ask the agent something interactively.

    python -m agent.cli --model ollama:qwen2.5:14b "Which region sold the most Software?"
    # add any other MCP server (e.g. your FastMCP TheMealDB server) alongside the env:
    python -m agent.cli --mcp "python path/to/meal_server.py" "Find a vegetarian pasta recipe"
"""
import argparse
import shlex
import sys
from pathlib import Path

from .llm import ToolChatModel
from .loop import Agent
from .mcp import MCPClient
from .memory import ContextManager, NoteStore, llm_summarizer
from .tools import Toolbox

ROOT = Path(__file__).resolve().parents[1]

p = argparse.ArgumentParser()
p.add_argument("task")
p.add_argument("--model", default="ollama:qwen2.5:14b")
p.add_argument("--mcp", action="append", default=[], help="extra MCP server command")
p.add_argument("--no-env", action="store_true", help="don't attach the company environment")
p.add_argument("--notes", default=str(ROOT / "memory" / "notes.json"))
p.add_argument("-v", "--verbose", action="store_true")
a = p.parse_args()

model = ToolChatModel(a.model)
tb = Toolbox()
if not a.no_env:
    tb.add_mcp(MCPClient([sys.executable, "-m", "env.server"], cwd=ROOT))
for cmd in a.mcp:
    tb.add_mcp(MCPClient(shlex.split(cmd)))
tb.add_memory(NoteStore(Path(a.notes)))
traj = Agent(model, tb, ContextManager(summarizer=llm_summarizer(model))).run(a.task)
if a.verbose:
    for i, s in enumerate(traj.steps, 1):
        for c in s.calls:
            print(f"[{i}] {c['name']}({c['arguments']}) -> {c['result'][:200]!r}")
print(traj.final or f"(stopped: {traj.stop_reason})")
print(f"\n{len(traj.steps)} steps · {traj.tool_calls} tool calls · {traj.input_tokens + traj.output_tokens} "
      f"tokens · ${traj.cost_usd:.4f} · {traj.seconds:.1f}s", file=sys.stderr)
tb.close()
