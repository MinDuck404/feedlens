# FeedLens roadmap

[Tiếng Việt](ROADMAP.vi.md) · [Contributing](CONTRIBUTING.md) · [Testing guide](docs/TESTING.md)

Draft for discussion. These are priorities, not release promises or dates. Difficulty: **S** = small, **M** = several connected changes, **L** = substantial design and validation. Completed features live in the [README](README.md).

## Now

| Priority | User problem | Done when | Difficulty |
|---|---|---|---|
| Tester onboarding | New testers need help installing, choosing scenarios and reporting safely. | A clean Windows machine can follow the release guide; a tester submits a reproducible, redacted report using the issue forms. | S |
| Tests on pull requests | Regressions may reach users before release. | Every PR runs backend pytest, frontend logic tests and a frontend build without real accounts or paid AI calls. | M |
| Agent scraping reports | Cloud users lack the skipped-post counts and stop reasons available locally. | Agents upload and persist a backward-compatible scrape report; old agents still work; contract tests cover both. | M |
| Broader platform validation | LinkedIn, X and Reddit have extractors, but fixtures alone do not establish live reliability. | A consent-based manual test matrix covers login, feed/search, original links, empty results and session expiry; sanitized fixtures cover failures found. | M |

## Next

| Priority | User problem | Done when | Difficulty |
|---|---|---|---|
| First-class local / compatible AI | Users want private or cheaper models without changing provider code. | Ollama and an OpenAI-compatible server pass classification, digest and Ask tests; endpoint/model configuration and unsupported capabilities are clear; local servers need no cloud credentials. | L |
| Scheduled runs | Users must launch every scan manually. | Users can enable, pause and inspect schedules; timezone, missed runs, overlap, expired sessions and sleeping local machines have defined behavior. | L |
| Useful notifications | A relevant job can be missed until the app is opened. | Opt-in Telegram or email supports score/topic thresholds, deduplication, delivery errors, protected tokens and content previews. Start with one channel. | M |

## Later

| Priority | User problem | Done when | Difficulty |
|---|---|---|---|
| Desktop distribution, including macOS | The source ZIP still needs bootstrap downloads and a terminal. | A packaged app installs, launches, updates and preserves data; macOS signing/notarization and Intel/Apple Silicon support are documented and tested. | L |
| Additional sources | Relevant posts and jobs also live outside the current four platforms. | Choose a source from tester demand; document access constraints, original-link behavior and fixture coverage before declaring support. Threads and job sites are candidates, not commitments. | L |

## What was checked

- `backend/feedlens/ai/providers/openai.py` uses the OpenAI SDK and Responses API. The SDK can read `OPENAI_BASE_URL`, so a compatible endpoint is **not entirely absent**. Discovery filters OpenAI-style model names; this is not verified Ollama support or a dedicated local-model setup flow.
- `.github/workflows/release.yml` already builds and tests the frontend on releases; no PR workflow running backend and frontend tests exists at this draft's creation.
- `backend/feedlens/runs/agent.py` uploads posts and progress but not `scrape_report`; local and server-cookie pipelines already produce it.
- No built-in scheduler or Telegram/email delivery module was found in `backend/feedlens/`.
- `start.sh` and release ZIPs already offer a source-based macOS path. A native signed app is a separate goal.
- How much live testing each non-Facebook platform has received cannot be established from source alone.

Community CLI tools and hosted scrapers inform these priorities; this draft makes no unverified feature, popularity or reliability comparisons. Propose concrete use cases through the feature-request form before expanding scope.
