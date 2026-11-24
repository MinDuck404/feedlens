# Run history

- Entry: `HistoryPage.tsx`; displays saved runs, source labels, status, and links to result tabs.
- Runs arrive through props; `App.tsx` loads them with the runs API.
- i18n prefixes: `hist`, `status`, `run`, `act`, `nav`.
- If history links open the wrong tab, inspect `HistoryPage.tsx` and `router.ts`.
- If source labels or dates look wrong, inspect `../../lib/logic.ts`.
