# Agent suite: `gpt4omini-baseline` (openai:gpt-4o-mini)

Success **75.0%** · pass^k **75.0%** · 24 tasks × 3 trials

| Category | Success |
|---|---|
| error_recovery | 50% |
| long_horizon | 100% |
| memory | 0% |
| multi_step | 78% |
| safety | 100% |
| single_tool | 100% |

Mean steps 3.29 · tool calls 2.56 · tool error rate 4.9% · tokens 1742 · $0.0003/task · p50 3.0s · p95 5.08s · compactions 0

## Failures

- **t09** (multi_step, stop=final): expected mention of 'South'. Final: 'The region with the highest software revenue from April through June 2025 was the East, with a total revenue of $390,351.69.'
- **t09** (multi_step, stop=final): expected mention of 'South'. Final: 'The region with the highest software revenue from April through June 2025 was the East, with a total revenue of $390,351.69.'
- **t09** (multi_step, stop=final): expected mention of 'South'. Final: 'The region with the highest software revenue from April through June 2025 was the East, with a total revenue of $390,351.69.'
- **t10** (multi_step, stop=final): expected mention of 'Mateo Garcia'. Final: 'The manager of the highest-paid employee who is not a director is Yara Nguyen.'
- **t10** (multi_step, stop=final): expected mention of 'Mateo Garcia'. Final: 'The manager of the highest-paid employee who is not a director is Yara Nguyen.'
- **t10** (multi_step, stop=final): expected mention of 'Mateo Garcia'. Final: "The highest-paid employee who is not a director is Yara Nguyen, and their manager's name is not available in the data."
- **t15** (error_recovery, stop=final): pattern "\\b(no|not|isn't|doesn't|does not|don't|unavailable|lack|cannot|can't)[^.]{0,80}(customer|table|data|information)". Final: 'We have 6 customers.'
- **t15** (error_recovery, stop=final): pattern "\\b(no|not|isn't|doesn't|does not|don't|unavailable|lack|cannot|can't)[^.]{0,80}(customer|table|data|information)". Final: 'We have 6 customers.'
- **t15** (error_recovery, stop=final): pattern "\\b(no|not|isn't|doesn't|does not|don't|unavailable|lack|cannot|can't)[^.]{0,80}(customer|table|data|information)". Final: 'We have 6 customers.'
- **t17** (memory, stop=final): pattern '\\d\\s?K\\b'. Final: 'The total revenue from Services products is $145,601.21.'
- **t17** (memory, stop=final): pattern '\\d\\s?K\\b'. Final: 'The total revenue from Services products is $145,601.21.'
- **t17** (memory, stop=final): pattern '\\d\\s?K\\b'. Final: 'The total revenue from Services products is $145,601.21.'
- **t18** (memory, stop=final): expected 142833.0 (±1.0); found []. Final: 'It seems I need to know your name to find the average salary on your team. Please provide your name or the name of your team.'
- **t18** (memory, stop=final): expected 142833.0 (±1.0); found []. Final: 'It seems I need to know your name to find the average salary for your team. Please provide your name or the name of your team.'
- **t18** (memory, stop=final): expected 142833.0 (±1.0); found []. Final: 'It seems I need to know the specific department name for your team to calculate the average salary. Please provide that information.'
- **t19** (memory, stop=final): expected 100 (±0.0); found [1.0, 2025.0, 0.0]. Final: 'In fiscal Q1 of 2025, there were 0 orders received.'
- **t19** (memory, stop=final): expected 100 (±0.0); found [1.0, 2025.0, 0.0]. Final: 'In fiscal Q1 of 2025, there were 0 orders received.'
- **t19** (memory, stop=final): expected 100 (±0.0); found [1.0, 2025.0, 0.0]. Final: 'In fiscal Q1 of 2025, there were 0 orders received.'
