# Browser profiles and cookies

- Entry: `profiles.py` detects browsers, opens isolated platform profiles, and verifies sessions.
- Cookie import parsing, validation, and hints live in `cookies.py`.
- Login windows fail or close unexpectedly: inspect `profiles.py`; browser HTTP state lives in `../routes/platforms.py`.
- Cache cleanup must preserve saved sessions and platform profile affinity.
- The start scripts import `profiles.py:warn_if_no_native_browser`.
- DOM extraction, JavaScript, and selector changes belong in `../scrapers/`.
