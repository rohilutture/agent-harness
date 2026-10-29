# Agent suite: `qwen14b-memidx` (ollama:qwen2.5:14b)

Success **44.4%** · pass^k **33.3%** · 3 tasks × 3 trials

| Category | Success |
|---|---|
| memory | 44% |

Mean steps 5.67 · tool calls 4.78 · tool error rate 2.3% · tokens 4563 · $0.0000/task · p50 4.47s · p95 7.88s · compactions 0

## Failures

- **t17** (memory, stop=final): pattern '\\d\\s?K\\b'. Final: 'The total revenue from Services products is $145,601.21.'
- **t17** (memory, stop=final): pattern '\\d\\s?K\\b'. Final: 'The total revenue from Services products is $145,601.21.'
- **t18** (memory, stop=final): expected 142833.0 (±1.0); found [75000.0]. Final: 'The average salary for the Sales department is $75,000.'
- **t18** (memory, stop=final): expected 142833.0 (±1.0); found [65000.0]. Final: 'จากการค้นหาข้อมูลในตาราง `employees`, ทีม Sales department มีค่าเฉลี่ยของเงินเดือนอยู่ที่ $65,000 ต่อปี (เมื่อปัดเศษเป็นจำนวนเต็ม)'
- **t18** (memory, stop=final): expected 142833.0 (±1.0); found [65000.0]. Final: 'จากการค้นหาข้อมูลในตาราง `employees`, ทีม Sales department มีค่าเฉลี่ยของเงินเดือนอยู่ที่ $65,000 ต่อปี (เมื่อปัดเศษเป็นจำนวนเต็ม)'
