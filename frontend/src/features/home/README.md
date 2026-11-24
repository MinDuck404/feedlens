# Home

- Screen: `#/`; entry: `HomeLanding.tsx`.
- Renders the welcome headline, edition date, local/cloud setup steps, and sign-in progress.
- Actions open the composer or settings through callbacks supplied by `App.tsx`.
- API: none directly; platform sign-in status arrives through props.
- i18n prefixes: `home.*` and the action labels `act.newRun` / `act.settings`.
- If welcome text or setup steps look wrong, inspect `HomeLanding.tsx` and the home locale namespace.
