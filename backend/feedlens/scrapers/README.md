# Platform collection

- Start with `registry.py` for platform selection and `base.py` for collection budgets, pacing, and verification.
- Facebook changed its layout? Edit `facebook/selectors.py` and `facebook/js/*.js`; orchestration and hover recovery live in `facebook/dom.py`.
- Facebook returns wrong links? Check `facebook/links.py`; missing GraphQL text/identity belongs in `facebook/stories.py`.
- LinkedIn feed extraction lives in `linkedin/scraper.py`; job cards and Jobs URLs live in `linkedin/jobs.py`.
- LinkedIn layout changes belong in `linkedin/selectors.py` and `linkedin/js/`.
- X and Reddit each own `scraper.py`, `selectors.py`, and `js/extract.js` in their platform folder.
- `scripts.py` loads packaged JavaScript once when its owning Python module is imported.
- Template placeholders map to CSS in each platform's `selectors.py`; keep selector changes there.
- Synthetic, network-blocked browser checks live in `backend/tests/test_scrapers.py` and `test_linkedin_jobs.py`.
