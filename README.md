<div align="center">

**English** · [Tiếng Việt](README.vi.md) · [简体中文](README.zh-CN.md)

# FeedLens

**Read less, know more.**

FeedLens browses your social feeds, groups, and search results with your own logged-in session.
Then AI sorts the posts, summarizes each topic, and picks out the jobs that fit your CV, laid out like a newspaper you can actually read.

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![React + Vite](https://img.shields.io/badge/react-vite-61DAFB?logo=react&logoColor=black)](frontend/)
[![AI: Claude · ChatGPT · Gemini](https://img.shields.io/badge/AI-Claude%20·%20ChatGPT%20·%20Gemini-AE3824)](#choosing-an-ai)
[![License: MIT](https://img.shields.io/badge/license-MIT-16120E)](LICENSE)

[Quick start](#quick-start) · [Features](#features) · [How it works](#how-it-works) · [Choosing an AI](#choosing-an-ai) · [Self-hosting](#self-hosting-in-the-cloud) · [Caveats](#caveats)

<img src="docs/screenshots/hero-digest-light.png" alt="The digest page of a run, laid out like a printed newspaper" width="900">

</div>

## Why FeedLens

Job groups, community groups, and news feeds post hundreds of items a day, and most of them are ads, memes, and reposts. FeedLens reads them for you and hands back a short digest: what is worth reading, which jobs match you, and a link to the original when you need it. It runs on your machine, in your browser, with your account.

## Features

| | |
|---|---|
| **4 platforms** | Facebook, LinkedIn, X (Twitter), Reddit: feeds, groups, or search results |
| **Newspaper-style digest** | Posts are grouped by type (jobs, tech, news, marketplace…), each with its own summary, plus an overall front page |
| **Your topics** | Define up to 12 custom topics; AI assigns a topic only when the post is genuinely relevant; a dedicated "Your topics" section sits atop the digest (even for topics with 0 posts); re-apply topics to past runs at any time |
| **Ask & search** | Full-text search across saved posts with structured filters (category, topic, date, jobs: remote/salary/location/score, GitHub links); Ask AI answers with verified citations [#id] pointing to real posts, or states when no matches are found |
| **Trends** | Post volume by category or topic over 7/30/90 days, viewed daily or weekly, compared to the prior period; click any point to open Ask & search for those posts |
| **Job matching from your CV** | Upload a PDF once; AI scores every job 0–100 on role, level, work mode (remote/hybrid/onsite), location, and salary. It also surfaces related roles (e.g. junior dev → IT helpdesk) and lists the skills you are missing |
| **Nothing lost when AI fails** | Scraped posts are saved before analysis; fix your key and press "Re-analyze" without scraping again |
| **Bring your own AI** | Claude, ChatGPT, Gemini, or an offline keyword classifier when you have no key |
| **Runs locally** | Sessions live in a dedicated Chrome profile and data in SQLite; only post text goes to the AI you choose |
| **3 languages** | UI and summaries in English, Tiếng Việt, or 中文 (follows your browser by default) |
| **Light / dark** | Cream paper by day, dark wood by night; follows your OS or toggle it in the sidebar |

<table>
  <tr>
    <td width="62%"><img src="docs/screenshots/posts-dark.png" alt="Post list in dark mode"></td>
    <td width="38%"><img src="docs/screenshots/mobile-dark.png" alt="Mobile layout"></td>
  </tr>
  <tr>
    <td><img src="docs/screenshots/jobs-light.png" alt="Jobs tab with match scores"></td>
    <td><img src="docs/screenshots/composer-light.png" alt="New run drawer"></td>
  </tr>
</table>

## Quick start

You need [Python 3.10+](https://www.python.org/downloads/) (tick *Add to PATH*), [Node.js LTS](https://nodejs.org), and Google Chrome.

1. Get the code: **Code → Download ZIP** and unzip, or `git clone https://github.com/MinDuck404/feedlens.git`.
2. **Windows:** double-click `start.bat`. **macOS/Linux:** run `./start.sh`.
   The first run takes a few minutes to install dependencies and build the UI. Your browser opens http://127.0.0.1:8765.
3. Click **Sign in** next to Facebook (on mobile, open the ☰ menu). A Chrome window opens; sign in as usual, including two-step verification. It closes itself when done.
4. **Settings** (gear) → **API keys**: add a Gemini, ChatGPT, or Claude key. Without a key the app falls back to keyword matching.
5. Looking for work? **Job profile** tab: upload your CV, review the summary, pick your criteria and the roles you are open to.
6. (Optional) **Topics** tab: create up to 12 personal tracking topics with custom keywords and colors.
7. Click **New run**, choose your feed or groups, then **Start**.

Close the terminal window (or press Ctrl+C) to stop the app.

> Want to see the UI with sample data before signing in anywhere? `cd backend && .venv\Scripts\feedlens demo`.

## How it works

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/diagrams/how-it-works-dark.svg">
  <img src="docs/diagrams/how-it-works.svg" alt="Your Chrome scrapes posts, raw posts are saved to SQLite, AI classifies and summarizes them, and the result becomes a digest">
</picture>

- **Scraping:** a real Chrome window with FeedLens's own profile scrolls like a reader. *Fast* mode pauses about 1 second; *Careful* scrolls slower.
- **Many groups:** save a list of groups and tick the ones to scan. "Posts" is **per group**; a run caps at `FEEDLENS_MAX_POSTS` (default 500). Broken groups are skipped.
- **Verification / checkpoints:** if a platform asks you to sign in again, the bot pauses and waits up to 10 minutes for you to finish in the Chrome window.
- **AI:** up to 4 batches in parallel, 20 posts per batch. Every provider uses the same JSON schema, so results look the same.
- **When AI fails mid-run:** raw posts are already in the database. The run shows the reason, lets you read and download the raw posts (.json/.md), and offers **Re-analyze** with another key or model.

### Job matching from your CV

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/diagrams/cv-matching-dark.svg">
  <img src="docs/diagrams/cv-matching.svg" alt="The CV PDF is parsed locally, AI builds a Markdown profile, and the profile is used to score each job post">
</picture>

- PDF text is extracted on your machine (`pypdf`). AI turns it into a Markdown profile and strips phone numbers, emails, and home addresses. **The PDF itself is never stored.**
- You set the criteria (remote/hybrid/onsite, locations, minimum salary, level) and switch on each related role you want to try.
- Every job gets a **Primary role / Related role / Stretch role** label, a reason, missing skills, and a warning when it breaks your criteria. The server caps scores: one broken criterion caps at 65, two at 30; related roles cap at 80, or 40 if you have not opted in.
- The profile is sent once per batch of 20 posts, not once per post.

### Asking AI about your archive

- **Understands the question as a filter:** AI translates your natural language question into structured filters (date range, platform, category, topics, job constraints).
- **Searches locally first:** The backend queries your local database (using SQLite full-text search FTS5) to find at most 40 candidate posts.
- **Grounded synthesis with citations:** If matching posts exist, AI writes a concise answer citing sources with `[#id]` pointing only to verified post IDs. Any fabricated IDs are automatically stripped.
- **Zero matches early exit:** When no posts match the query, the system immediately returns a "no posts found" message without making an unnecessary second AI call.
- **Lean payload:** Only the question and truncated excerpts of matching posts are sent to the AI; your whole database is never transferred.

## Choosing an AI

| Provider | Get a key at | Force a model (local) |
|---|---|---|
| Claude | console.anthropic.com | `ANTHROPIC_MODEL` |
| ChatGPT | platform.openai.com | `OPENAI_MODEL` |
| Gemini | aistudio.google.com | `GEMINI_MODEL` |

- The model list in "New run" comes straight from the provider's API with your key (cached 10 minutes, with a refresh button).
- "Default" picks `gemini-3.5-flash-lite` / `gpt-5-mini` / `claude-opus-5-5` when your key has it, otherwise the newest fast model. On 429/5xx the app retries 3 times (3s, 6s, 12s), then moves to the next model.
- OpenAI-compatible servers (OpenRouter, LM Studio…): set `OPENAI_BASE_URL` (local only).
- Adding a provider: subclass `AIProvider` with `complete_json()` and `list_models()`, then register it in `ai/registry.py`.

## Caveats

> [!WARNING]
> Automated browsing **violates the terms** of Facebook, LinkedIn, and X, and accounts can get checkpointed. Keep it personal and small-scale, and consider a secondary account.

- FeedLens is **read-only**: it never posts, comments, or messages. Your password never passes through the app.
- The bot runs in a visible Chrome window by default. Headless mode is often blocked (Reddit blocks headless browsers when signed out). FeedLens does not try to evade anti-bot systems.
- Post text is sent to the AI provider you choose. `backend/data/` holds session cookies: **never share or commit it**.
- Social sites change their markup often. If a platform returns 0 posts, fix its JS extractor in `backend/feedlens/scrapers.py`.

## FAQ

**Can I use it without an AI key?**
Yes. Posts are sorted by an offline keyword classifier. You get no AI summaries, and job scores only count matched keywords.

**How long does a run take?**
It depends on the number of posts and the speed setting. *Fast* mode pauses about 1 second per scroll, plus AI time per batch of 20 posts.

**A platform returns 0 posts?**
Usually the site changed its markup. Check that platform's JS in `backend/feedlens/scrapers.py`, or open an issue.

**Where is my data?**
In `backend/data/`: Chrome sessions in `profiles/`; posts, results, your CV profile, and encrypted API keys in `feedlens.db`; the encryption key in `secret.key`. This folder is git-ignored. Do not send it to anyone. Delete it to wipe everything.

**Is my CV stored?**
The PDF is not. Only the Markdown profile you approved, with contact details removed. Delete it any time from the Job profile tab.

**What if the AI fails halfway?**
Your scraped posts are kept. Fix the key or switch models in Settings, open the run, and press **Re-analyze**.

**Does Ask AI send my entire database to the AI?**
No. It only sends your question along with short excerpts of up to 40 posts matching your local SQLite FTS5 search and filters. If zero posts match, no request is sent to the AI.

## For developers

<details>
<summary><b>Manual setup and CLI</b></summary>

Requirements: Python ≥ 3.10, Node ≥ 20, Google Chrome (or Edge).

```bash
cd backend && uv venv && uv pip install -e ".[dev]"
copy backend\.env.example backend\.env
cd frontend && npm install && npm run build
```

Put AI keys in `backend/.env` or enter them in the web UI. Run the backend (it also serves the built UI at http://127.0.0.1:8765):

```bash
cd backend && .venv\Scripts\feedlens serve --open
```

While working on the UI, also run the Vite dev server (http://localhost:5173, proxies `/api` to the backend):

```bash
cd frontend && npm run dev
```

Scrape from the command line, e.g. two job groups with ChatGPT:

```bash
cd backend && .venv\Scripts\feedlens run facebook --type group --source https://www.facebook.com/groups/aaa --source bbb -n 60 --jobs -k python -k remote --ai openai
```

Tests:

```bash
cd backend && .venv\Scripts\python -m pytest -q
cd frontend && node --test tests/logic.test.cjs
```

</details>

<details>
<summary><b>Project layout</b></summary>

```
backend/            Python, FastAPI: API, scraper (Playwright), AI layer, DB
  feedlens/
    api.py          REST API (/api/...), also serves frontend/dist when built
    messages.py     stable error/progress codes the UI translates to vi/en/zh
    auth.py         accounts, session tokens, agent tokens (cloud mode)
    crypto.py       password hashing (scrypt), API key encryption (Fernet)
    agent.py        `feedlens agent`: takes jobs from the cloud, scrapes on the user's machine
    ai/             anthropic_provider · openai_provider · gemini_provider · registry
    db/             SQLAlchemy: tables.py (schema) + repository.py (queries)
    browser.py      per-platform Chrome profiles, interactive sign-in
    scrapers.py     URLs + JS extractors per platform, human-like scrolling
    analyzer.py     classify, extract jobs, summarize (shared by every AI)
    pipeline.py     scrape → classify → summarize, in the background, with progress
    job_profile.py  CV → Markdown profile, criteria, related roles (adjacent_roles.json)
    profile_api.py  /api/profile: save, read, delete the profile; CV analysis
    topics_api.py   /api/topics: CRUD custom topics, re-tag past runs
    trends_api.py   /api/trends: aggregate post volume by category/topic
    search_api.py   /api/search: FTS5 search & Ask AI with verified citations
  tests/
frontend/           React + Vite + TypeScript + Tailwind
  src/components/     AskPage.tsx · TrendsPage.tsx · RunView · Settings · TopicSettings
  src/components/ui/  shared Dialog/Sheet, Button, Skeleton, EmptyState
  src/i18n.tsx        vi/en/zh dictionaries
  tests/              logic tests (node --test)
docker-compose.yml  Postgres (optional)
```

</details>

<details>
<summary><b>Database: SQLite or Postgres</b></summary>

SQLite at `backend/data/feedlens.db` by default. For Postgres:

```bash
docker compose up -d
cd backend && uv pip install -e ".[postgres]"
```

Then set `DATABASE_URL=postgresql+psycopg://feedlens:feedlens@localhost:5432/feedlens` in `backend/.env`. Tables are created on startup.

</details>

## Self-hosting in the cloud

There is no public instance; FeedLens is designed to run on your own machine. This section is for anyone who wants to host a multi-user instance.

<details>
<summary><b>Architecture and deployment</b></summary>

| Part | Runs on | Config |
|---|---|---|
| Frontend | GitHub Pages | `.github/workflows/pages.yml` (re-enable it in the Actions tab), repo variable `VITE_API_URL` |
| Backend | Render (free tier, sleeps after 15 idle minutes) | `render.yaml` (Blueprint) |
| Database | Neon Postgres (free) | `DATABASE_URL` on Render |

For Railway, `backend/railway.json`, `frontend/railway.json`, and both Dockerfiles are ready.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/diagrams/cloud-architecture-dark.svg">
  <img src="docs/diagrams/cloud-architecture.svg" alt="An agent on the user's machine takes jobs from the FastAPI backend with an fla_ token; the backend stores data in Postgres; the frontend is on GitHub Pages">
</picture>

Scraping **always runs on the user's machine**, because it needs a real Chrome, their session, and a residential IP (datacenter IPs get checkpointed fast). The server holds no social cookies unless you enable Server (cookie) mode below.

Flow:

1. Sign up on the web app.
2. **Settings → API keys:** paste a key. The server validates it by listing models, encrypts it (Fernet, key derived from `FEEDLENS_SECRET`), and stores it. The UI only shows the last 4 characters.
3. **Settings → Agent:** create an `fla_…` token (shown once; only its hash is stored) and run the agent:

   ```bash
   cd backend && .venv\Scripts\feedlens agent --server https://your-api.example.com --token fla_xxx
   ```

4. First time only, sign the agent in to the social site: `.venv\Scripts\feedlens login facebook`.
5. Click **New run → Start**. The agent polls every 2 seconds, scrapes in Chrome, and uploads posts; the server analyzes them with your key.

Each account only sees its own runs, posts, and keys. The "New run" form and group list are saved to the account (`/api/preferences`). `feedlens push` (scrape once and upload, no queue) uses the same token.

Backend environment variables:

| Variable | Value |
|---|---|
| `FEEDLENS_MODE` | `cloud` |
| `DATABASE_URL` | Postgres connection string (Neon: `postgresql://…?sslmode=require`) |
| `FEEDLENS_SECRET` | random string ≥ 32 chars; signs sessions and encrypts API keys. **Never change it** once users exist |
| `FEEDLENS_ALLOW_SIGNUP` | `true` or `false` |
| `FEEDLENS_CORS` | frontend origin, e.g. `https://you.github.io` |

In cloud mode the server **ignores** API keys from the environment, so other users cannot spend the host's quota. Without `FEEDLENS_SECRET` the backend locks the whole API. 10 wrong passwords in 15 minutes (per IP or per email) triggers a temporary block. The frontend only needs `VITE_API_URL` at build time.

</details>

<details>
<summary><b>Server (cookie) mode: scrape without an agent</b></summary>

The server opens a headless Chromium with the login cookies you saved.

> [!CAUTION]
> Cookies are used from a datacenter IP, unlike the machine you normally use. Facebook/LinkedIn may ask for verification, sign you out, or **lock the account**. Use a secondary account. Cookies are as powerful as a password.

1. On your machine: `feedlens login facebook`, then upload the cookies:

   ```bash
   cd backend && .venv\Scripts\feedlens cookies push facebook
   ```

   This reads cookies from FeedLens's own Chrome profile (not your main Chrome). Alternatively: **Settings → Server scraping → Paste cookies** (Cookie-Editor JSON, `cookies.txt`, or `c_user=…; xs=…`).
2. **Settings → Check:** the server tries to open the home page with the cookies (about 10–30 seconds).
3. **New run → Run with: Server (cookie) → Start.**

- Cookies are encrypted at rest and never returned to the UI; only the last 4 digits of the account ID are shown.
- The server blocks images/video/fonts and runs **one** browser at a time (other runs queue).
- If the platform asks for sign-in or verification, the run stops and the cookie is marked **Expired**. Sign in again locally and upload fresh cookies.
- Disable this mode with `FEEDLENS_SERVER_SCRAPE=false`. The Docker image ships headless Chromium, and `/api/health` reports `"browser": true`.

</details>

## Roadmap

- [ ] Scheduled morning runs + Telegram/email alerts for jobs scoring ≥ 80
- [x] Upload a CV (PDF) for more accurate job matching
- [x] Ask questions over collected data ("any remote React jobs over 30M VND this week?")
- [x] Topic trend charts over time
- [ ] Ollama (fully local AI), Threads, TopCV/ITviec
- [ ] Desktop package (Tauri) so no terminal is needed

## License

[MIT](LICENSE)
