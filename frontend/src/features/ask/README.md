# Search and ask

- Entry: `AskPage.tsx`; renders saved-post search, filters, questions, answers, and citations.
- API: search, ask, topics, and available search sources.
- i18n prefixes: `ask`, `search`, `act`, `topics`, `cat`, `posts`.
- If a query or filter behaves incorrectly, inspect `AskPage.tsx` and `../../lib/search.ts`.
- If answer citations link to the wrong post, inspect `textParts` in `../../lib/search.ts`.
