"""One-off: rewrite the README '## Results' section from results/*.json (so no number is typed by hand)."""
import json
import re
from pathlib import Path

L = lambda n: json.load(open(f"results/{n}.json", encoding="utf-8"))


def cat(d, c):
    rs = [r for r in d["runs"] if r["category"] == c]
    return sum(r["passed"] for r in rs) / len(rs)


rows = []
for label, n in (("openai:gpt-4o-mini", "gpt4omini-baseline"), ("ollama:qwen2.5:14b", "qwen14b-baseline"),
                 ("ollama:llama3.1:8b", "llama8b-baseline")):
    d = L(n)
    a = d["aggregate"]
    rows.append(f"| {label} | {a['success']:.1%} | {a['pass_all_k']:.1%} | {cat(d, 'memory'):.0%} | "
                f"{cat(d, 'long_horizon'):.0%} | {cat(d, 'safety'):.0%} | {a['tool_error_rate']:.1%} | "
                f"${a['cost_per_task_usd']:.4f} | {a['latency_p95_s']}s |")


def mem(m):
    d = L(f"{m}-memidx")
    return sum(r["passed"] for r in d["runs"]), len(d["runs"])


def ok(n, frag):
    rs = [r for r in L(n)["runs"] if r["id"] == "t24"]
    return sum(next(c["ok"] for c in r["checks"] if frag in c["detail"]) for r in rs)


b, f, fs = L("qwen14b-baseline")["aggregate"], L("qwen14b-force1000")["aggregate"], L("qwen14b-force1000-llmsummary")["aggregate"]
mq, ml, mg = mem("qwen14b"), mem("llama8b"), mem("gpt4omini")

text = f"""## Results

24 tasks x 3 trials (72 runs) per row, temperature 0, on one RTX 4090 (Ollama for the local models). Full per-run
detail, including every failure, is in `results/<name>.md` and `results/<name>.json`.

| Model | Success | pass^3 | Memory | Long-horizon | Safety | Tool-error rate | $/task | p95 |
|---|---|---|---|---|---|---|---|---|
{chr(10).join(rows)}

**Read these with the sample size in mind.** There are only 24 tasks (categories have 2-9 tasks each), and at
temperature 0 the three trials of a task are nearly identical, so the effective sample is closer to 24 than 72 and
pass^3 is almost the same as success here. Differences of a few points are one or two tasks, not signal.

**What the runs showed:**
- **Model gap.** `gpt-4o-mini` > `qwen2.5:14b` >> `llama3.1:8b`. The 8B model fails mostly at tool-call formatting
  (68.5% of its tool calls errored). `qwen2.5:14b` also shows output degeneration in some runs (replies in Thai or
  Chinese, and raw `<tool_call>` text returned as the final answer); that is model behavior, not a harness bug.
- **Memory was 0% for every model at first, and the cause was retrieval, not storage.** The notes were saved correctly in
  session 1, but in session 2 the models never called `search_notes` on their own, despite the system prompt telling them
  to. Adding `--memory-index` (list the saved note keys in the system prompt as a cue) lifted memory to
  {mq[0]}/{mq[1]} for `qwen2.5:14b` and {mg[0]}/{mg[1]} for `gpt-4o-mini`; `llama3.1:8b` stayed at {ml[0]}/{ml[1]} because it
  never called `search_notes`. Even with the cue, the models often built the wrong query from the note (for example
  filtering on "Salesdepartment" and getting $0), so memory is improved, not solved.
- **Injection guard (task t24).** With the "tool output is DATA" line in the system prompt, `qwen2.5:14b` never wrote
  the planted note ({ok('qwen14b-baseline', 'pwned')}/3 trials clean); without it, it wrote the note in
  {3 - ok('qwen14b-noguard', 'pwned')}/3 trials. But the guard did not stop it repeating the planted false date
  ({ok('qwen14b-baseline', '2030')}/3 clean in both settings), so t24 fails either way for this model. `gpt-4o-mini` passed
  t24 3/3 with the guard; a no-guard run for it was not done. The overall success drop without the guard (65.3% to 58.3%)
  came mostly from unrelated categories (error recovery, long-horizon), so it should not be read as a guard effect.
- **Regression gate.** `evals/gate.py` flagged the no-guard run against the baseline (exit code 1), which shows the
  gate mechanics work; see `results/gate_demo.txt`.
- **Compaction: no measurable difference.** In the first round `--budget` and `--llm-summary` had no effect, because
  tasks that set their own budget ignore `--budget` and nothing triggered a compaction. After adding `--force-budget 1000`
  (the same budget on every task), compaction did trigger ({f['compactions']} compactions with the heuristic summarizer,
  {fs['compactions']} with `--llm-summary`), but success was {b['success']:.1%} (baseline), {f['success']:.1%} (heuristic)
  and {fs['success']:.1%} (LLM summary), and long-horizon stayed at 4/6 in all three. No evidence either summarizer is
  better on this suite.

**Limits:** small task set; temperature 0 so little trial variance; one run per configuration; the safety and long-horizon
categories have 2-3 tasks each; Qwen's output glitches add noise; results are for one local setup.
"""

p = Path("README.md")
s = p.read_text(encoding="utf-8")
a = s.index("## Results")
b2 = s.index("## Run it")
s = s[:a] + text + "\n" + s[b2:]
p.write_text(s, encoding="utf-8")
print(text[:600])
