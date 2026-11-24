# API contracts

- `client.ts` owns HTTP requests, authentication, downloads, and ordered preference writes.
- `types.ts` defines request, response, and stored-record contracts.
- Features call the exported `api` and `auth` objects directly.
- If a request fails or reaches the wrong route, inspect `client.ts`.
- If a response shape changes, inspect `types.ts` and the affected feature.
