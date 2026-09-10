# True Cost of Living & Net Pay Compare — Integration Guide

## Keeping state tax data current

There's no free live API for state income tax brackets (API Ninjas gates that behind a paid plan). Instead, `get_state_tax_brackets()` tries, in order:

1. **Live scrape** of Tax Foundation's rates page (`get_state_tax_brackets_live()`), cached for 300 days once successful. Locates the table by nearby heading text ("...Income Tax Rates and Brackets...") rather than a hardcoded Tablepress table ID, since that ID is specific to this year's table and will change when Tax Foundation republishes. Validates the parse before trusting it -- rejects anything that doesn't yield ~51 states/DC or that contains an implausible rate, and falls through instead of returning bad data.
2. **Stale cache** of a previously successful scrape, if the live attempt fails.
3. **The bundled static file** (`utils/state_tax_2026.json`), as a last resort.

**Honesty about what's actually verified here:** I validated the row-parsing *algorithm* against a synthetic fixture built from the real page's actual rendered content (Claude fetched the live page during development and hand-checked the parser reproduces Alabama's 3-bracket structure, Alaska's no-tax state, and Arizona's flat rate exactly). What I could **not** verify is the real page's exact HTML tag/class structure, because this sandbox can't reach `taxfoundation.org` (confirmed: the scraper correctly falls through to the static file when the request is blocked, which is the right failure behavior). **The first time you run this against the live internet, check `data_quality.state_tax` in a response -- if it says `"live"`, the scraper works. If it keeps saying `static_dataset_*`, check your logs for the scrape-failure warning.**

- **Automatic staleness detection** (of the *static fallback file specifically*): a rolling 365-day threshold that logs a warning and surfaces it in the API response once the bundled JSON gets old -- relevant mainly if the live scrape stops working and you're relying on the fallback for a long stretch.
- **Manual check without starting the app**: `python3 check_state_tax_freshness.py` (checks the static file's age; exit code 0/1).
- **If the live scraper breaks** (Tax Foundation changes their page layout): paste the failure warning into a fresh conversation with Claude and ask it to inspect the current page structure and fix `_find_state_tax_table()`/`parse_state_tax_table()` in `utils/col_utils.py` -- or, at minimum, ask it to re-fetch current brackets and regenerate `state_tax_2026.json` so the fallback tier stays current even if the scraper needs a real fix.

## Solving for required salary (no need to enter a "To" salary)

The "To" salary field is optional. Location-based expenses (rent, utilities, gas, groceries) don't depend on salary — only net take-home pay does — so instead of guessing a target salary and comparing, the app can solve for it directly: `solve_required_salary()` uses bisection search to find the exact gross salary at the target location that reproduces your current monthly disposable income.

- **Leave "To" salary blank**: the required salary IS the answer, shown as the headline ("You'd need to earn at least $X/year in Austin, TX to match your current lifestyle").
- **Enter an actual offer**: you get both the real comparison at that salary *and* the required-salary figure alongside it, so you can see the gap between what's offered and what's actually needed.

Performance note: the solver calls the tax calculation ~60 times per request (an iterative search, not a lookup). Since state tax comes from a live scrape with no guaranteed uptime, a naive implementation would retry that live HTTP call on every iteration — I caught this in testing (26 failed scrape attempts logged for a single comparison) and fixed it with a 1-hour negative cache on scrape/API failures, shared by `get_state_tax_brackets_live()` and `get_federal_tax_brackets()`. A full solve now completes in well under half a second even with all live sources unreachable.

## Insurance (added per your clarification)

Two new expense line items, at your request, since disposable income should account for insurance costs too:

- **Auto insurance**: real state-level data now, from ValuePenguin's full-coverage monthly premium table (`utils/state_auto_insurance_2026.json`, sourced, dated Jul 8 2026). This one's static-only, no live scrape tier — unlike Tax Foundation's single clean rates table, auto insurance publishers mix multiple overlapping tables on one page (cheapest company, most expensive, by age, by coverage type), which made "find *the* table" meaningfully harder to do reliably without inspecting the real page. If this matters more to you later, the same staleness-check pattern used for state tax could be extended here.
- **Health insurance**: a flat $120/month national average (employee's share of an employer-sponsored single-coverage premium, per KFF's 2025 Employer Health Benefits Survey), **not location-varying**. I looked for state-level data on the *employee-paid portion* specifically and couldn't find a clean, citable source — state breakdowns that do exist are for ACA marketplace self-purchased plans, a ~6x larger and structurally different number that would badly overstate this for someone with employer coverage. Flagged explicitly in the UI and in `excluded_from_model` so it doesn't read as more precise than it is.

## Files in this drop

| File | Action |
|---|---|
| `check_state_tax_freshness.py` | **New.** Standalone freshness check, runnable without starting Flask. |
| `utils/col_utils.py` | **New.** Core calculation engine. |
| `utils/col_cache.py` | **New.** SQLite persistent cache (survives Flask debug-reloader restarts). |
| `utils/state_tax_2026.json` | **New.** Sourced state income tax brackets, single filer, as of Jan 1 2026 (Tax Foundation). Refresh annually — see note in the file. |
| `utils/state_auto_insurance_2026.json` | **New.** Sourced state auto insurance rates (ValuePenguin). Static only, no live tier — see below. |
| `app.py` | **Modified.** Added `from utils.col_utils import calculate_takehome_and_expenses` and the `/api/col-compare` route. Diff against your original with any diff tool. |
| `templates/jobs.html` | **Modified.** Added the `$` icon next to the existing climate icon, and a new `#colCompareModal`. |
| `static/jobs.js` | **Modified.** Added click handlers for the new icon, 401(k) slider, and compare submit button. |

Drop these into your repo at the matching paths (`utils/col_utils.py` next to your existing `utils.py`/`utils/` package, etc.) and diff `app.py`/`jobs.html`/`jobs.js` against your originals to merge — I started from the exact files you uploaded, so the diffs should be small and localized.

## Setup

1. **No new dependencies** — `requests`, `beautifulsoup4`, `lxml` are already in your `pyproject.toml`.
2. **`col_cache.db`** will be created automatically on first run, in your project root. Add it to `.gitignore`.
3. **API keys (all free, all optional):**

   | Env var | Used for | Get it at |
   |---|---|---|
   | `API_NINJAS_KEY` | Federal tax brackets (live) | api-ninjas.com — free signup, no card |
   | `OPENEI_API_KEY` | Utility rates (live) | `developer.nlr.gov` — free signup, no card (note: domain moved from `developer.nrel.gov` in 2026) |
   | `EIA_API_KEY` | Gas prices (live) | eia.gov/opendata — free signup, no card |

   **The feature works with zero keys configured** — it just runs entirely on the "estimated" fallback tier (national averages) instead of live/location-specific data. Add keys incrementally; each one independently upgrades its own data source.

   Set them however you already manage config, e.g. a `.env` file loaded before `app.run()`, or your shell environment.

## What's NOT modeled (by design, see BuildBrief.md decisions)

- Local/municipal income tax (Philly, NYC, Cincinnati, etc.)
- 401(k) employer match
- Health insurance premiums
- Mortgage/buy-vs-rent — rent only
- Real auto insurance/DMV quotes — approximated via a flat national estimate

These are surfaced to the user in the modal's disclaimer text and in the API response's `excluded_from_model` field, not hidden.

## Testing without live API access

I ran the calculation engine end-to-end in a sandboxed environment with no internet access to the external APIs (Nominatim/Numbeo were blocked there), and confirmed it degrades cleanly to the "estimated" tier without crashing — tax math checked out against hand-calculated progressive brackets. **I was not able to test the live API tiers (API Ninjas, OpenEI, EIA, real Nominatim/Numbeo) or exercise the actual Flask route / modal in a browser**, since I don't have your full repo running. Before relying on this:

1. Run the Flask app locally and click the `$` icon on a real job card — check the browser console for JS errors.
2. Test `/api/col-compare` directly with `curl` or Postman using a couple of real city/state pairs.
3. If you add API keys, verify one live call per source (check `data_quality` in the JSON response — it'll say `"live"` vs `"estimated"` per field).
4. Numbeo scraping is the most fragile piece (no official API, markup can change) — if `data_quality.housing_groceries` always comes back `"estimated"`, that's the first thing to check with a print/debug session against the actual HTML Numbeo returns for your test cities.

## Known open items (not addressed here, per BuildBrief.md)

- Employer 401(k) match, health insurance, local tax, rent-vs-buy — all explicitly out of scope per your earlier decisions, not partially implemented.
- `state_tax_2026.json` needs a manual refresh once a year (each February when Tax Foundation republishes).
