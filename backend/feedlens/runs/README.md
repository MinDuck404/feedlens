# Run execution

- Entry: `pipeline.py` collects sources, saves checkpoints, runs analysis, and publishes progress.
- `source_modes.py` validates and normalizes platform sources and collection budgets.
- `agent.py` handles remote-agent polling and handoff; `server_runner.py` handles cookie-backed server collection.
- Export serializers live in `export.py`.
- Missing or duplicated paid reads: inspect checkpoints and controls in `pipeline.py`.
- Wrong source URLs or limits: inspect `source_modes.py`; scraping details belong in `../scrapers/`.
