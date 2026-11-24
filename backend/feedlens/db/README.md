# Persistence

- Entry: `repository.py:Database` composes domain persistence methods and owns engine/session setup.
- `tables.py` contains SQLAlchemy tables; `repos/` contains users, keys/usage, runs, posts, topics, and search methods.
- Database upgrades and SQLite foreign-key setup live in `repository.py`.
- Missing run checkpoints: inspect `repos/runs.py` and `repos/posts.py`.
- User isolation or FTS behavior: inspect `repos/search.py`; quota usage: inspect `repos/keys.py`.
- Callers import `Database` from `feedlens.db.repository`.
