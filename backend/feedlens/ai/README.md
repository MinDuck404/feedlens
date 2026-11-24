# AI providers and quotas

- Entry: `registry.py` resolves enabled credentials, providers, models, and cached model lists.
- `base.py` defines provider interfaces and errors; `providers/` contains Gemini, OpenAI, and Anthropic adapters.
- Quota accounting, backoff, candidate rotation, and request scheduling live in `scheduler.py` and `limits.py`.
- When Google reports overload or quota errors, inspect `providers/gemini.py`, then `scheduler.py`.
- Classification prompts and digest logic belong in `../analysis/`.
