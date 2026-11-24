# Trends

- Entry: `TrendsPage.tsx`; owns filters, URL/storage defaults, loading, and request cancellation.
- `TrendsChart.tsx` renders accessible charts and links selected periods to search.
- API: trends data for the selected window, bucket, and topic.
- i18n prefixes: `trends`, `act`, `hist`, `cat`, `nav`.
- If a filter reloads stale data, inspect `TrendsPage.tsx`.
- If chart geometry or colors look wrong, inspect `TrendsChart.tsx` and `../../lib/trends.ts`.
