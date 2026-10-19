"""Run the task suite against a model: k trials per task, scored, timed, costed.

    python -m evals.run_suite --model ollama:qwen2.5:14b --trials 3 --name qwen14b-v1

Outputs results/<name>.json (every trajectory + aggregates) and results/<name>.md.
Metrics:
  success      mean pass rate over all trials (pass@1)
  pass^k       share of tasks passed in ALL k trials (reliability, not luck)
  steps, tool calls, tool error rate, tokens, $ cost, latency p50/p95, compactions
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path

import numpy as np
import yaml

from agent.llm import ToolChatModel
from agent.loop import Agent
from agent.mcp import MCPClient
from agent.memory import ContextManager, NoteStore, llm_summarizer
from agent.tools import Toolbox
from env.server import DB, build_db

from .checks import check

ROOT = Path(__file__).resolve().parents[1]


def env_client() -> MCPClient:
    return MCPClient([sys.executable, "-m", "env.server"], timeout=30, cwd=ROOT)


def run_task(task: dict, model, client: MCPClient, budget: int, max_steps: int,
             summarize: bool) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        notes = NoteStore(Path(tmp) / "notes.json")  # fresh memory per trial
        trajs = []
        for prompt in task["sessions"]:
            tb = Toolbox()
            tb.add_mcp(client)
            tb.add_memory(notes)
            ctx = ContextManager(task.get("context_budget", budget),
                                 summarizer=llm_summarizer(model) if summarize else None)
            trajs.append(Agent(model, tb, ctx, max_steps=max_steps).run(prompt))
        final = trajs[-1].final
        results = [(c, *check(c, final, notes, str(DB))) for c in task["checks"]]
    agg = lambda f: sum(f(t) for t in trajs)
    return {"id": task["id"], "category": task["category"],
            "passed": all(ok for _, ok, _ in results),
            "checks": [{"check": c, "ok": ok, "detail": d} for c, ok, d in results],
            "final": final, "stop_reason": trajs[-1].stop_reason,
            "steps": agg(lambda t: len(t.steps)), "tool_calls": agg(lambda t: t.tool_calls),
            "tool_errors": agg(lambda t: t.tool_errors),
            "input_tokens": agg(lambda t: t.input_tokens), "output_tokens": agg(lambda t: t.output_tokens),
            "cost_usd": agg(lambda t: t.cost_usd), "seconds": agg(lambda t: t.seconds),
            "compactions": agg(lambda t: t.compactions), "maskings": agg(lambda t: t.maskings),
            "repeats_blocked": agg(lambda t: t.repeats_blocked),
            "trajectories": [asdict(t) for t in trajs]}


def aggregate(rows: list[dict]) -> dict:
    by_task, by_cat = defaultdict(list), defaultdict(list)
    for r in rows:
        by_task[r["id"]].append(r["passed"])
        by_cat[r["category"]].append(r["passed"])
    secs = [r["seconds"] for r in rows]
    calls = sum(r["tool_calls"] for r in rows)
    return {"n_tasks": len(by_task), "n_runs": len(rows),
            "success": round(float(np.mean([r["passed"] for r in rows])), 4),
            "pass_all_k": round(float(np.mean([all(v) for v in by_task.values()])), 4),
            "by_category": {k: round(float(np.mean(v)), 4) for k, v in sorted(by_cat.items())},
            "by_task": {k: round(float(np.mean(v)), 4) for k, v in sorted(by_task.items())},
            "mean_steps": round(float(np.mean([r["steps"] for r in rows])), 2),
            "mean_tool_calls": round(calls / len(rows), 2),
            "tool_error_rate": round(sum(r["tool_errors"] for r in rows) / max(calls, 1), 4),
            "mean_tokens": round(float(np.mean([r["input_tokens"] + r["output_tokens"] for r in rows])), 1),
            "cost_per_task_usd": round(float(np.mean([r["cost_usd"] for r in rows])), 6),
            "latency_p50_s": round(float(np.percentile(secs, 50)), 2),
            "latency_p95_s": round(float(np.percentile(secs, 95)), 2),
            "compactions": sum(r["compactions"] for r in rows),
            "stop_reasons": dict(sorted({s: sum(r["stop_reason"] == s for r in rows)
                                         for s in {r["stop_reason"] for r in rows}}.items()))}


def markdown(name: str, model: str, agg: dict, rows: list[dict]) -> str:
    lines = [f"# Agent suite: `{name}` ({model})\n",
             f"Success **{agg['success']:.1%}** · pass^k **{agg['pass_all_k']:.1%}** · "
             f"{agg['n_tasks']} tasks × {agg['n_runs'] // max(agg['n_tasks'], 1)} trials\n",
             "| Category | Success |", "|---|---|"]
    lines += [f"| {k} | {v:.0%} |" for k, v in agg["by_category"].items()]
    lines += ["", f"Mean steps {agg['mean_steps']} · tool calls {agg['mean_tool_calls']} · "
              f"tool error rate {agg['tool_error_rate']:.1%} · tokens {agg['mean_tokens']:.0f} · "
              f"${agg['cost_per_task_usd']:.4f}/task · p50 {agg['latency_p50_s']}s · "
              f"p95 {agg['latency_p95_s']}s · compactions {agg['compactions']}",
              "", "## Failures", ""]
    for r in rows:
        if not r["passed"]:
            bad = "; ".join(c["detail"] for c in r["checks"] if not c["ok"])
            lines.append(f"- **{r['id']}** ({r['category']}, stop={r['stop_reason']}): {bad}. "
                         f"Final: {r['final'][:160]!r}")
    return "\n".join(lines) + "\n"


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="ollama:qwen2.5:14b")
    p.add_argument("--tasks", default=str(ROOT / "evals" / "tasks.yaml"))
    p.add_argument("--trials", type=int, default=3)
    p.add_argument("--only", nargs="*")
    p.add_argument("--budget", type=int, default=12000, help="context token budget")
    p.add_argument("--max-steps", type=int, default=15)
    p.add_argument("--llm-summary", action="store_true", help="compaction summaries by the model")
    p.add_argument("--name", required=True)
    a = p.parse_args(argv)

    if not DB.exists():
        build_db(DB)
    tasks = yaml.safe_load(Path(a.tasks).read_text())
    if a.only:
        tasks = [t for t in tasks if t["id"] in a.only]
    model = ToolChatModel(a.model)
    client = env_client()
    rows = []
    t0 = time.time()
    try:
        for task in tasks:
            for trial in range(a.trials):
                r = run_task(task, model, client, a.budget, a.max_steps, a.llm_summary)
                r["trial"] = trial
                rows.append(r)
                print(f"{task['id']} trial {trial}: {'PASS' if r['passed'] else 'FAIL'} "
                      f"({r['steps']} steps, {r['seconds']:.1f}s)", flush=True)
    finally:
        client.close()
    agg = aggregate(rows)
    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    (out / f"{a.name}.json").write_text(json.dumps(
        {"name": a.name, "model": a.model, "trials": a.trials, "wall_s": round(time.time() - t0, 1),
         "aggregate": agg, "runs": rows}, indent=1, default=str))
    md = markdown(a.name, a.model, agg, rows)
    (out / f"{a.name}.md").write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
