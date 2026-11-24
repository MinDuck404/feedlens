# Shared application contracts

- Entry: `config.py` loads settings and resolves backend/data paths.
- `models.py` defines request and persisted payload contracts.
- Session/token authentication lives in `auth.py`; encryption and password hashing live in `crypto.py`.
- User-facing error/progress codes live in `messages.py`.
- Configuration or data-path failures: inspect `config.py`; rejected login tokens: inspect `auth.py`.
- HTTP handlers belong in `../routes/`, and database operations belong in `../db/`.
