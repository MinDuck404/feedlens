# Create a run

- Entry: `Composer.tsx`; owns drafts, preferences, validation, submission, and sheet lifecycle.
- `SourceMode.tsx` renders platform modes, saved sources, source entry, and mode-specific fields.
- `JobCriteria.tsx` renders job filtering, keyword chips, and profile notes.
- `Controls.tsx` owns the model picker and composer field controls.
- API: providers, models, sessions, topics, profile, and create run.
- i18n prefixes: `cmp`, `kw`, `profile`, `topics`, `act`, `error`.
- If switching modes loses values or serialization fails, inspect `Composer.tsx` and `lib/platformModes.ts`.
