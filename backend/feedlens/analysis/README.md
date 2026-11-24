# Analysis

- Entry: `analyzer.py:get_analyzer` selects the configured implementation.
- `llm.py` owns AI classification, retry handling, and digest generation; `heuristic.py` owns offline behavior.
- Output schemas, prompts, and batch estimates live in `prompts.py`; topic matching lives in `topics.py`.
- Post identity and duplicate grouping live in `duplicates.py`.
- For missing paid reads or incomplete responses, inspect `llm.py` and the quota scheduler in `../ai/scheduler.py`.
