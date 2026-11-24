# Shared logic

- `logic.ts` handles source labels, timestamps, run status, job presentation, and scrape timing.
- `platformModes.ts` owns mode definitions, drafts, validation, migration, and request serialization.
- `categories.ts` and `topics.ts` own shared labels, colors, and topic filtering.
- `search.ts` owns search filters, citations, and question history.
- `trends.ts` owns trend chart geometry and colors.
- If several screens disagree on a value, start with the corresponding helper here.
