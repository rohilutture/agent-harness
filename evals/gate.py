"""Regression gate: compare a candidate suite run against a baseline; exit 1 on regression.

    python -m evals.gate --baseline results/baseline.json --candidate results/pr-123.json

A change to the prompt, memory policy, model or tools fails the gate if:
  * overall success drops by more than --max-success-drop (default 5 points), or
  * any task that passed ALL baseline trials now fails ALL candidate trials
    (a hard break, even if the average looks fine), or
  * cost per task or p95 latency grows by more than --max-cost-increase /
    --max-latency-increase (defaults 25%).
Agents are stochastic, so the gate compares multi-trial runs, and uses a points
threshold rather than "any drop", to avoid failing on noise.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def compare(base: dict, cand: dict, max_success_drop=0.05, max_cost_increase=0.25,
            max_latency_increase=0.25) -> tuple[bool, list[str], str]:
    b, c = base["aggregate"], cand["aggregate"]
    problems = []
    if c["success"] < b["success"] - max_success_drop:
        problems.append(f"success {b['success']:.1%} -> {c['success']:.1%} "
                        f"(drop > {max_success_drop:.0%})")
    broken = [t for t, v in b["by_task"].items() if v == 1.0 and c["by_task"].get(t, 0.0) == 0.0]
    if broken:
        problems.append(f"hard breaks (always passed, now always fails): {', '.join(broken)}")
    if b["cost_per_task_usd"] > 0 and \
            c["cost_per_task_usd"] > b["cost_per_task_usd"] * (1 + max_cost_increase):
        problems.append(f"cost/task ${b['cost_per_task_usd']:.4f} -> ${c['cost_per_task_usd']:.4f}")
    if c["latency_p95_s"] > b["latency_p95_s"] * (1 + max_latency_increase):
        problems.append(f"p95 latency {b['latency_p95_s']}s -> {c['latency_p95_s']}s")

    rows = ["| Metric | Baseline | Candidate |", "|---|---|---|"]
    for k in ["success", "pass_all_k", "mean_steps", "tool_error_rate", "mean_tokens",
              "cost_per_task_usd", "latency_p95_s"]:
        rows.append(f"| {k} | {b[k]} | {c[k]} |")
    for cat in sorted(set(b["by_category"]) | set(c["by_category"])):
        rows.append(f"| {cat} | {b['by_category'].get(cat, '—')} | {c['by_category'].get(cat, '—')} |")
    fixed = [t for t, v in b["by_task"].items() if v == 0.0 and c["by_task"].get(t, 0) == 1.0]
    report = "\n".join(rows) + (f"\n\nNewly fixed: {', '.join(fixed)}" if fixed else "")
    return not problems, problems, report


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--baseline", required=True)
    p.add_argument("--candidate", required=True)
    p.add_argument("--max-success-drop", type=float, default=0.05)
    p.add_argument("--max-cost-increase", type=float, default=0.25)
    p.add_argument("--max-latency-increase", type=float, default=0.25)
    a = p.parse_args(argv)
    ok, problems, report = compare(json.loads(Path(a.baseline).read_text()),
                                   json.loads(Path(a.candidate).read_text()),
                                   a.max_success_drop, a.max_cost_increase, a.max_latency_increase)
    print(report)
    print("\nGATE:", "PASS" if ok else "FAIL")
    for pr in problems:
        print(" -", pr)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
