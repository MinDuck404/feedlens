# FeedLens architecture

A map for finding code fast. Each folder below also has its own `README.md` with the entry file and debugging hints.

## How a run flows

```
Browser UI (frontend/src)                        Backend (backend/feedlens)
features/composer ──POST /api/runs──▶ routes/runs.py ──▶ runs/pipeline.py
                                                           │ 1. scrapers/<platform>/  (your browser profile, browser/profiles.py)
                                                           │ 2. db/repos/posts.py     (raw posts saved before any AI call)
                                                           │ 3. analysis/ + ai/       (classify, summarize, score jobs)
features/run ◀──GET /api/runs/{id}── routes/runs.py ◀──────┘    progress + results
```

## Backend: `backend/feedlens/`

| Folder | What lives here | Start with |
|---|---|---|
| `api.py` | FastAPI app, error handlers, serves the built UI (entry point) | `api.py` |
| `cli.py`, `demo.py` | Command line (`feedlens …`) and demo data | |
| `core/` | Settings, encryption, login sessions, error codes, Pydantic models | `config.py`, `models.py` |
| `routes/` | One file per URL group: `auth`, `preferences`, `platforms`, `ai_keys`, `runs`, `agent`, `profile`, `search`, `topics`, `trends` | the file named after the URL |
| `runs/` | Run pipeline, source validation, exports, cloud agent, server-side scraping | `pipeline.py` |
| `scrapers/` | One folder per platform: `facebook/`, `linkedin/`, `x/`, `reddit/`, each with `scraper.py`, `selectors.py`, `js/*.js` | `registry.py`, `base.py` |
| `browser/` | Per-platform browser profiles, Chrome/Edge detection, sign-in window, cookies | `profiles.py` |
| `ai/` | Provider adapters (`providers/gemini.py`, `openai.py`, `anthropic.py`), quota scheduling and key rotation | `registry.py`, `scheduler.py` |
| `analysis/` | Prompts, AI and offline analyzers, topics, duplicate grouping | `analyzer.py` |
| `jobs/` | CV profile and job match scoring | `scoring.py` |
| `db/` | SQLAlchemy tables and one repository file per data type (`repos/users`, `keys`, `runs`, `posts`, `topics`, `search`) | `repository.py` |

## Frontend: `frontend/src/`

| Screen (URL) | Folder |
|---|---|
| Home (`#/`) | `features/home/` |
| New run drawer | `features/composer/` |
| A run: Summary / Jobs / Posts (`#/runs/12`, `/jobs`, `/posts`) | `features/run/` |
| History (`#/history`) | `features/history/` |
| Trends (`#/trends`) | `features/trends/` |
| Ask & search (`#/ask`) | `features/ask/` |
| Sidebar: accounts, previous runs | `features/sidebar/` |
| Settings: API keys, job profile, topics, cookies | `features/settings/` |
| Sign in (cloud mode) | `features/auth/` |

Shared code: `api/` (HTTP client and types), `lib/` (pure helpers), `components/ui/` (buttons, dialogs, selects), `i18n/` (UI text).

**UI text:** `i18n/locales/{vi,en,zh}/<screen>.ts`. The first line of each file names the screen that uses it. A key keeps its prefix (`run.*` → `run.ts`, `cmp.*` → `composer.ts`). Add every new key to all three languages; `frontend/tests/logic.test.cjs` checks this.

## When something breaks

| Symptom | Look here |
|---|---|
| A platform returns 0 posts or wrong text after a site redesign | `scrapers/<platform>/selectors.py` and `scrapers/<platform>/js/*.js`; see `scrapers/README.md` |
| Wrong or missing link to the original post (Facebook) | `scrapers/facebook/links.py`, then `stories.py` |
| Sign-in window, "no browser found", session lost | `browser/profiles.py`, `routes/platforms.py` |
| "Quota", "overloaded (503)", model switching, a key not used | `ai/scheduler.py`, `ai/providers/gemini.py`; the run page lists a reason per key |
| AI returns empty or cut-off results | `analysis/llm.py`, `analysis/prompts.py` |
| Job scores look wrong | `jobs/scoring.py`; the CV profile comes from `jobs/profile.py` |
| CV upload fails | `routes/profile.py`, then `jobs/profile.py` |
| Same job shown twice | `analysis/duplicates.py` |
| Run stuck or progress wrong | `runs/pipeline.py`, then `routes/runs.py` |
| Wrong or missing text on screen | `frontend/src/i18n/locales/<lang>/<screen>.ts` |
| An API returns an error code | `core/messages.py` (codes) and the matching file in `routes/` |

## Tests

- Backend: `cd backend && .venv/Scripts/python -m pytest -q` (no browser, no real accounts, fake AI providers).
- Frontend: `cd frontend && npm run build && node --test tests/*.test.cjs`.
