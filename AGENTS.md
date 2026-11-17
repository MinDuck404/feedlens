# FeedLens: rules for coding agents

Follow existing project patterns first. Each rule names a file that already follows it.
Agent team workflow (who owns which task, commits, screenshots) comes from the lead, not this file.

## Frontend
- Keep React components as function components and call hooks unconditionally at the top level; App uses local hook state and effects (`frontend/src/App.tsx`).
- Keep component state local unless multiple routes genuinely share it; Composer owns form state while App owns workspace state (`frontend/src/components/Composer.tsx`, `frontend/src/App.tsx`).
- Type component props, API payloads, and platform unions; `RunRequest` and `ModeOptions` define literal contracts (`frontend/src/types.ts`).
- Narrow untrusted input at runtime before use; platform-mode sources validate schemes, hosts, credentials, ports, paths, and identifiers (`frontend/src/platformModes.ts`).
- Use existing UI primitives and theme tokens; Composer uses `SegmentedControl`, `Select`, `Button`, while CSS defines shared surface and accent tokens (`frontend/src/components/Composer.tsx`, `frontend/src/index.css`).
- Use semantic labels and controls; Composer associates visible labels with text inputs and uses fieldsets, buttons, and toggles (`frontend/src/components/Composer.tsx`).
- Keep user-visible copy in the shared locale dictionaries; all supported locales use matching keys and `useI18n` (`frontend/src/i18n.tsx`).
- Keep Vite configuration focused on the existing React/Tailwind plugins and relative deployment base (`frontend/vite.config.ts`).
- Prefer existing Tailwind utilities and tokens; extend the project theme only when a reusable design token is needed (`frontend/src/index.css`).

## Backend
- Use Pydantic models for request and stored-record contracts; `RunRequest` validates modes and typed options (`backend/feedlens/models.py`).
- Keep synchronous work in `def` routes or offload it from async routes; session checks and model lookups use `run_in_threadpool` (`backend/feedlens/api.py`).
- Return API errors with explicit HTTP status and structured error codes; the shared handlers map Starlette and Pydantic validation errors (`backend/feedlens/api.py`).
- Validate platform hosts, paths, and mode options before browser navigation or queue side effects (`backend/feedlens/source_modes.py`; `backend/feedlens/api.py`).
- Keep browser profiles isolated by platform and close contexts in `finally`; cache cleanup must not remove session data (`backend/feedlens/browser.py`).
- Keep database operations behind `Database`; scope user-owned queries and group writes in session transactions (`backend/feedlens/db/repository.py`).
- Bind user-provided values in SQL expressions; repository FTS binds both query and owner (`backend/feedlens/db/repository.py`).
- Enable SQLite foreign-key checks for each SQLite connection (`backend/feedlens/db/repository.py`).
- Preserve backward-compatible defaults and add migrations rather than rewriting saved requests; legacy inference and additive column migration are explicit (`backend/feedlens/source_modes.py`; `backend/feedlens/db/repository.py`).

## Test
- Run frontend checks from `frontend/`: `npm run build` and `node --test tests/*.test.cjs` (`frontend/package.json`; `frontend/tests/logic.test.cjs`).
- Run backend tests from `backend/`: `.venv/Scripts/python -m pytest -q`; pytest discovers `tests/` (`backend/pyproject.toml`).
- Prefer deterministic fake providers, temporary databases, and synthetic HTML; source-mode tests require no browser/live account/paid AI (`backend/tests/test_source_modes.py`; `backend/tests/test_linkedin_jobs.py`).
- When testing DOM extraction, use headless Chromium and abort all network requests; fixtures must not use real profiles or social accounts (`backend/tests/test_scrapers.py`).
- Preserve existing legacy behavior with focused regression tests when changing request formats or analysis (`backend/tests/test_source_modes.py`; `backend/tests/test_analysis_recovery.py`).

## i18n
- Supported UI locales are Vietnamese, English, and Chinese; add the same key and interpolation variables to all dictionaries (`frontend/src/i18n.tsx`).
- Resolve strings through `useI18n().t` or `translate`, not inline UI literals (`frontend/src/i18n.tsx`).
- Keep locale changes reactive and set the document language (`frontend/src/i18n.tsx`).
- Verify dictionaries have identical keys and interpolation placeholders (`frontend/tests/logic.test.cjs`).

## Sources
Distilled from sanjeed5/awesome-cursor-rules-mdc (react, typescript, vite, tailwind, fastapi, python, playwright, sqlite) and PatrickJS/awesome-cursorrules (react, typescript-vite-tailwind, python-fastapi). Rules that conflict with this codebase were dropped.
