# lab_summary.md

Starting from zero-shot prompts for three tasks — sentiment classification,
product description generation, and structured data extraction — I ran each
prompt 5, 10, and 15 times to diagnose failure patterns before attempting
any improvement. The most important finding was that zero-shot prompts failed
not because the model gave wrong answers, but because it gave unpredictably
formatted answers: sentiment came back as sentences instead of single words,
descriptions ranged from 50 to 300 words, and extraction used a different
structure every run. Adding explicit format constraints in v2 reduced variance
significantly but did not fully solve consistency. The biggest jump came in v3
when few-shot examples were added to sentiment and product description (showing
the model the exact format expected), and Chain-of-Thought reasoning was added
to data extraction (forcing the model to reason step by step before producing
the JSON). Few-shot worked best where the output format is rigid and
non-negotiable; CoT worked best where the task requires identifying information
that may appear in different positions or phrasing across inputs. If I were
doing this again I would start with temperature=0 for all classification tasks
from the beginning rather than discovering mid-lab that it removed most of the
remaining variance, and I would write the failure analysis format before running
any tests so the documentation stayed consistent across all three tasks.