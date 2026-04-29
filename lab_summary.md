# lab_summary.md

Starting from zero-shot prompts for three tasks — sentiment classification,
product description generation, and structured data extraction — I ran each
prompt 5, 10, and 15 times to diagnose failure patterns before attempting
any improvement. The most important finding was that zero-shot prompts failed
not because the model gave wrong answers, but because it gave unpredictably
formatted answers: sentiment came back as full sentences instead of single
words, descriptions ranged from 50 to 300 words, and extraction used a
different structure every run. Adding explicit format constraints in v2
reduced variance significantly but did not fully solve consistency — the
biggest jump came in v3 when few-shot examples were added to sentiment and
product description (showing the model the exact format expected), and
Chain-of-Thought reasoning was added to data extraction (forcing step-by-step
identification before producing JSON). Few-shot worked best where the output
format is rigid and non-negotiable; CoT worked best where the task requires
identifying information that may appear in different positions across inputs.
The temperature experiments confirmed that classification tasks should use
temperature=0 (100% consistent) while generation tasks benefit from 0.5–0.7
for natural variation; the multi-task prompt showed a small but acceptable
consistency loss (~5–10%) compared to dedicated prompts, making it viable for
prototyping but not for high-traffic production. If I were doing this again I
would set temperature=0 for all classification tasks from the beginning and
write the failure analysis format before running any tests so documentation
stayed consistent across all three tasks.