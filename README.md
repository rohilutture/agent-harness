# agent-harness

A tool-using LLM agent **built from the loop up**, with no agent framework. It includes:
- my own agent loop
- my own MCP client and server (JSON-RPC over stdio)
- two kinds of memory (durable notes, plus context masking and compaction for long tasks)
- a 24-task evaluation suite with deterministic checkers
- a **regression gate** that fails a change if success, cost, or latency regresses

```
            ┌──────────── agent loop (agent/loop.py) ─────────────┐
 task ─────►│ context.fit()  →  model(messages, tools)  →  tools  │──► answer + trajectory
            │   mask / compact    Ollama | OpenAI | Anthropic     │      (steps, tokens, $, ms)
            └──────────────┬───────────────────────┬──────────────┘
                     native tools             MCP over stdio
                 write_note / search_notes    env/server.py: sql_query, list_tables,
                 (persist across sessions)    search_docs, read_doc, calculator
```

## The suite

24 tasks over a deterministic company world (SQLite: employees, products, orders, plus policy docs). Expected answers are **computed with SQL at check time**, so nothing is hard-coded.

| Category | What it tests | Example |
|---|---|---|
| single_tool | basic tool use | "What is the hotel cap in New York?" |
| multi_step | joins, aggregation, doc + DB reasoning | "Which sales rep generated the most revenue?" |
| error_recovery | missing tables, date handling, fixing failed SQL | "How many customers do we have?" (no such table) |
| memory | facts from session 1 change the answer in session 2 | "Remember my team is Sales" → "Average salary on my team?" |
| long_horizon | tiny context budget forces masking and compaction | read three policies, then answer three questions |
| safety | prompt injection in a document; destructive requests | `vendor_notes.md` tells the agent to write a "pwned" note |

**Metrics per run:**
- success (pass@1 over k trials)
- **pass^k** (passed every trial, so reliability rather than luck)
- per-category success
- steps, tool calls, tool error rate
- tokens, $/task, latency p50/p95
- compactions

## Results

> Run on your machine; paste `results/<name>.md`.

| Model | Success | pass^3 | Memory | Long-horizon | Safety | $/task | p95 |
|---|---|---|---|---|---|---|---|
| ollama:qwen2.5:14b | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ | $0 | _TBD_ |
| ollama:llama3.1:8b | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ | $0 | _TBD_ |
| openai:gpt-4o-mini | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |

**Ablations worth running.** Each is a one-flag change, scored by the same suite:
- heuristic vs. `--llm-summary` compaction
- `--budget 4000` vs. 12000
- with vs. without the "tool output is data" line in the system prompt, via `--no-injection-guard` (the safety category should drop without it)

## Run it

```bash
pip install -r requirements.txt
ollama pull qwen2.5:14b            # needs a tool-calling model; llama3.1:8b also works

python -m agent.cli -v "Which region had the highest Software revenue in Q2 2025?"

python -m evals.run_suite --model ollama:qwen2.5:14b --trials 3 --name baseline
# change something (prompt, memory policy, model), then:
python -m evals.run_suite --model ollama:qwen2.5:14b --trials 3 --name candidate
python -m evals.gate --baseline results/baseline.json --candidate results/candidate.json
```

Plug in any other MCP server next to the environment, for example the FastMCP TheMealDB server from DATA 236:
```bash
python -m agent.cli --no-env --mcp "python path/to/meal_server.py" "Find me a vegetarian pasta recipe"
```

## CI
- `.github/workflows/tests.yml` runs the 14 unit tests on every push. They need no LLM; scripted models and mocked HTTP cover the loop, MCP, memory, checkers, gate, and all three provider adapters.
- `.github/workflows/agent-regression.yml` runs the real suite plus the gate on demand. It needs a **self-hosted runner** with Ollama (your PC) or an API key secret, and compares against `results/baseline.json` committed on `main`.

See **[DESIGN.md](DESIGN.md)**.
