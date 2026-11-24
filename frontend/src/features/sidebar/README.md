# Workspace navigation

- Entry: `Sidebar.tsx`; renders desktop and mobile navigation, recent runs, and platform accounts.
- `PlatformRow` handles account checks, login, and manual verification completion.
- `STATUS_CLS` supplies the run-status colors also used by history.
- API: platform check/login/finish and agent connection status.
- i18n prefixes: `nav`, `plat`, `status`, `run`, `act`, `agent`, `lang`, `theme`, `cmp`, `error`.
- If platform status or sign-in controls look wrong, inspect `PlatformRow` in `Sidebar.tsx`.
