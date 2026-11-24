# Run results

- Entry: `RunView.tsx`; loads and polls a run, handles deletion, downloads, and reruns.
- `InProgress.tsx` and `RetryAnalysis.tsx` handle progress, quota details, stop, and model changes.
- `Done.tsx` selects digest, jobs, and posts; `runPostFilters.ts` owns post-filter URLs.
- `DigestView.tsx`, `JobsBoard.tsx`, and `PostList.tsx` render the result tabs.
- API: run detail/delete/download, topics, providers/models, retry analysis, and stop analysis.
- i18n prefixes: `run`, `tab`, `tier`, `job`, `posts`, `topics`, `profile`, `act`, `error`, `cmp`, `plat`.
- If counts or source timing look wrong, inspect `ScrapeReportLine.tsx` and `../../lib/logic.ts`.
