# Account and workspace settings

- Entry: `Settings.tsx`; owns the settings sheet, provider loading, and preference updates.
- `AIProviderKeys.tsx` manages API keys, priority, plans, validation, and usage.
- `CookieSessions.tsx` manages saved platform sessions; `JobProfileSettings.tsx` manages CV and job criteria.
- `TopicSettings.tsx` manages topics, tests, and background analysis progress.
- `PreferenceMenus.tsx` supplies language and theme controls for settings, login, and sidebar.
- API: providers/keys, sessions, profile/CV, topics, preferences, and agent connection.
- i18n prefixes: `set`, `profile`, `topics`, `theme`, `lang`, `act`, `error`, `cmp`, `plat`.
- If one settings tab fails, start with its named file; for shared loading, inspect `Settings.tsx`.
