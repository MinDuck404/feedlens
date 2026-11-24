# HTTP routes

- `../api.py` creates the app, installs error handlers, includes routers, and serves the local frontend.
- Start with the module matching the URL: `auth`, `preferences`, `platforms`, `ai_keys`, `runs`, `agent`, `profile`, `search`, `topics`, or `trends`.
- `dependencies.py:db` accesses the app database; router factories receive the same dependency.
- Login throttling belongs in `auth.py`; browser login/session state belongs in `platforms.py`.
- Missing run progress or analysis controls: inspect `runs.py`, then `../runs/pipeline.py`.
- Key management, including legacy provider URLs, belongs in `ai_keys.py`.
- CV uploads live in `profile.py`; topic retag jobs live in `topics.py`.
