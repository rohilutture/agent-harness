# Agent suite: `gpt4omini-memidx` (openai:gpt-4o-mini)

Success **44.4%** · pass^k **33.3%** · 3 tasks × 3 trials

| Category | Success |
|---|---|
| memory | 44% |

Mean steps 5.44 · tool calls 3.78 · tool error rate 0.0% · tokens 2712 · $0.0005/task · p50 5.25s · p95 6.18s · compactions 0

## Failures

- **t17** (memory, stop=final): pattern '\\d\\s?K\\b'. Final: 'The total revenue from Services products is $145,601.21.'
- **t17** (memory, stop=final): pattern '\\d\\s?K\\b'. Final: 'The total revenue from Services products is $145,601.21.'
- **t17** (memory, stop=final): pattern '\\d\\s?K\\b'. Final: 'The total revenue from Services products is $145,601.21.'
- **t18** (memory, stop=final): expected 142833.0 (±1.0); found [0.0]. Final: 'The average salary on your team (Sales department) is $0.'
- **t18** (memory, stop=final): expected 142833.0 (±1.0); found [0.0]. Final: 'The average salary on your team (Sales department) is $0.'
