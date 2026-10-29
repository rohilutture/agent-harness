# Agent suite: `llama8b-memidx` (ollama:llama3.1:8b)

Success **0.0%** · pass^k **0.0%** · 3 tasks × 3 trials

| Category | Success |
|---|---|
| memory | 0% |

Mean steps 4.0 · tool calls 2.0 · tool error rate 50.0% · tokens 1970 · $0.0000/task · p50 0.91s · p95 3.28s · compactions 0

## Failures

- **t17** (memory, stop=final): expected 145601.21 (±291.20242); found []; pattern '\\d\\s?K\\b'. Final: 'Let me check the schema to see if the table exists.\n\n{"name": "list_tables", "parameters": {}}'
- **t17** (memory, stop=final): expected 145601.21 (±291.20242); found []; pattern '\\d\\s?K\\b'. Final: 'Let me check the schema to see if the table exists.\n\n{"name": "list_tables", "parameters": {}}'
- **t17** (memory, stop=final): expected 145601.21 (±291.20242); found []; pattern '\\d\\s?K\\b'. Final: 'Let me check the schema to see if the table exists.\n\n{"name": "list_tables", "parameters": {}}'
- **t18** (memory, stop=final): expected 142833.0 (±1.0); found []. Final: 'Let me check the schema to see if the column name is actually "team" or something else.\n\n{"name": "list_tables", "parameters": {}}'
- **t18** (memory, stop=final): expected 142833.0 (±1.0); found []. Final: 'Let me check the schema to see if the column name is actually "team" or something else.\n\n{"name": "list_tables", "parameters": {}}'
- **t18** (memory, stop=final): expected 142833.0 (±1.0); found []. Final: 'Let me check the schema to see if the column name is actually "team" or something else.\n\n{"name": "list_tables", "parameters": {}}'
- **t19** (memory, stop=final): expected 100 (±0.0); found []. Final: 'It seems that the `fiscal_year` column does not exist in the `orders` table. Let me check the schema.\n\n{"name": "list_tables", "parameters": {"schema": "orders"'
- **t19** (memory, stop=final): expected 100 (±0.0); found []. Final: 'It seems like the `fiscal_year` column does not exist in the `orders` table. Let me check the schema.\n\n{"name": "list_tables", "parameters": {"schema": "orders"'
- **t19** (memory, stop=final): expected 100 (±0.0); found []. Final: 'It seems like the `fiscal_year` column does not exist in the `orders` table. Let me check the schema.\n\n{"name": "list_tables", "parameters": {"schema": "orders"'
