# Sign in and registration

- Entry: `Login.tsx`; renders authentication forms, error messages, language, and theme controls.
- API: login and registration through `../../api/client.ts`.
- i18n prefixes: `login`, `act`, `error`, `lang`, `theme`.
- If credentials are rejected or registration fails, inspect `Login.tsx` and `../../api/client.ts`.
- Authenticated workspace state and logout handling remain in `App.tsx`.
