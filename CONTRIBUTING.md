# Contributing to FeedLens

[Roadmap](ROADMAP.md) · [Manual testing / Hướng dẫn test](docs/TESTING.md)

Bug reports and sanitized test results are welcome; you do not need to write code. For a new integration or a large change, open a feature request first to agree on scope.

## Development setup

Install Git, Python 3.10+ (3.11 recommended), Node.js 20+ and Google Chrome. In PowerShell:

```powershell
git clone https://github.com/MinDuck404/feedlens.git
cd feedlens
python -m venv backend/.venv
backend/.venv/Scripts/python -m pip install -e "./backend[dev]"
Copy-Item backend/.env.example backend/.env
cd frontend
npm ci
npm run build
cd ..
```

Do not overwrite an existing `.env`. Enter keys through Settings if preferred; no paid AI key is required for automated tests or offline classification.

Start the backend from the root in one terminal (also serves the built UI on port 8765):

```powershell
backend/.venv/Scripts/feedlens serve --open
```

For UI development, use another terminal:

```powershell
cd frontend
npm run dev
```

Vite proxies `/api` to the backend. On macOS/Linux create the venv with `python3`; replace `backend/.venv/Scripts/python` with `backend/.venv/bin/python` and `Scripts/feedlens` with `bin/feedlens`. User-facing bootstrap: `start.bat` / `./start.sh`.

## Checks before a pull request

From the root, isolate test storage from your archive. Close this terminal afterwards before starting your normal app; these variables apply to this terminal.

```powershell
$env:FEEDLENS_DATA_DIR = Join-Path $env:TEMP "feedlens-tests"
$env:DATABASE_URL = "sqlite:///:memory:"
backend/.venv/Scripts/python -m pytest -q backend/tests
cd frontend
node --test tests/logic.test.cjs
npm run build
```

The equivalent backend command from `backend/` is `.venv/Scripts/python -m pytest -q`. Tests use fake providers, temporary databases and browser fixtures; never substitute real accounts or live AI calls into the suite. For scraper changes, add a minimal sanitized fixture. For UI changes, check mobile/desktop, light/dark and vi/en/zh. Include redacted screenshots and the checks actually run. Manual testing is described in [TESTING](docs/TESTING.md).

## Change and commit conventions

- Keep each PR focused; explain the user problem, resulting behavior, verification and known limits.
- Follow surrounding code and test helpers. Add regression coverage for logic changes; avoid dependencies for trivial helpers.
- Use short, imperative commit subjects, such as `Fix missing Facebook page permalinks`. Existing history uses plain subjects; Conventional Commits are not required.
- Keep unrelated reformatting separate. Maintainers review and merge; a PR does not promise acceptance or a release date.

## Secrets and personal data

**Never commit or attach `backend/data/`, browser profiles, cookies, `feedlens.db`, `secret.key`, `.env`, API keys, agent tokens or a CV.** `backend/data/` and `backend/.env` are ignored, but custom directories elsewhere may not be. Check `git diff --cached` and `git status` before committing. Never force-add these files.

Inspect and redact debug HTML/JSON, logs and screenshots before sharing. An ignored file is not automatically safe to share. Follow the testing guide and prefer synthetic fixtures. If a credential was exposed, revoke/rotate it immediately and contact the maintainer without reposting it publicly.
