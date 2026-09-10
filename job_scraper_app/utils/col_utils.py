"""
True Cost of Living / Net Pay comparison engine.

Called from app.py's /api/col-compare route. Computes an estimated monthly
take-home pay and monthly fixed expenses for a given (salary, city, state),
so two locations can be compared side by side.

KNOWN SCOPE LIMITATIONS (deliberate, per project decision):
  - Housing is RENT ONLY. No mortgage/buy-vs-rent modeling.
  - No employer 401(k) match. Only the employee's own contribution is modeled.
  - No health insurance premium deduction / plan comparison.
  - No local/municipal income tax (Philly, NYC, Cincinnati, etc.). Federal +
    state only. This under-counts take-home pay in the ~10 states with local
    income taxes -- see utils/state_tax_2026.json footnote (a).
  - Auto insurance is a state-level average (utils/state_auto_insurance_2026.json),
    not a personalized quote based on age/vehicle/driving record.
  - Housing rent is a county-level HUD Fair Market Rent (1BR), and the
    grocery-cost adjustment is a BEA state Regional Price Parity index
    scaled against a national-average grocery basket -- neither is a
    line-item observed price the way the old Numbeo scrape was.

RELIABILITY PATTERN (per every data source below):
    live API call -> cached value (fresh) -> cached value (stale) -> a
    conservative hardcoded national-average estimate, tagged "estimated": True
  A result should never be None; every field is always populated, and
  "data_quality" tells the caller/UI which tier each number came from.
"""
import logging
import os
import re
from datetime import date, datetime
from urllib.parse import quote

import requests

from utils.col_cache import cache_get, cache_get_stale, cache_set
from utils.climate_utils import get_lat_lon  # reuse existing Nominatim geocoder

logger = logging.getLogger(__name__)

# How old the static state-tax dataset can get before we flag it as stale.
# Tax Foundation republishes this table roughly annually, so 365 days is a
# reasonable rolling threshold -- this number does NOT need to change every
# year, only utils/state_tax_2026.json's contents do.
STATE_TAX_STALE_AFTER_DAYS = 365

_stale_warning_logged = False  # avoid spamming logs on every request

# ---------------------------------------------------------------------------
# Config -- all keys optional; every function degrades gracefully without one
# ---------------------------------------------------------------------------
API_NINJAS_KEY = os.environ.get("API_NINJAS_KEY", "")
OPENEI_API_KEY = os.environ.get("OPENEI_API_KEY", "")
EIA_API_KEY = os.environ.get("EIA_API_KEY", "")
# Free bearer token from https://www.huduser.gov/portal/dataset/fmr-api.html
HUD_FMR_API_TOKEN = os.environ.get("HUD_FMR_API_TOKEN", "")
# Free registered key from https://apps.bea.gov/API/signup/
BEA_API_KEY = os.environ.get("BEA_API_KEY", "")
# The Census geocoder (used to turn lat/lon into a county FIPS for the HUD
# and BEA lookups below) is a free, keyless public API -- no config needed.

FICA_RATE = 0.0765  # Social Security + Medicare, fixed by law, not a "rate" that needs refreshing

# Conservative national-average fallbacks, used only when live API + cache
# (fresh and stale) all fail. Deliberately rough -- the goal is "never crash
# the endpoint," not precision.
CONSERVATIVE_FALLBACK = {
    "monthly_rent_1br": 1700,
    "electricity_cents_per_kwh": 16.5,
    "monthly_kwh_usage": 900,
    "gas_price_per_gallon": 3.30,
    "monthly_groceries": 400,
    "monthly_registration_misc": 30,  # DMV fees etc; auto insurance is now separately state-sourced below
}

# Employee's out-of-pocket share of an employer-sponsored single-coverage
# health premium. National average only -- KFF's 2025 Employer Health
# Benefits Survey gives a solid national figure ($1,440/yr, ~16% of the
# total premium) but no reliable state-by-state breakdown of the
# employee-paid *portion* specifically (state breakdowns that exist are for
# ACA marketplace self-purchased plans, a different and ~6x larger number --
# using that here would badly overstate this for people with employer
# coverage). Source: KFF 2025 Employer Health Benefits Survey,
# https://www.kff.org/health-costs/2025-employer-health-benefits-survey/
# Refresh this manually roughly annually when KFF publishes the new survey.
HEALTH_INSURANCE_MONTHLY_EMPLOYEE_SHARE = 120  # ~$1,440/yr per KFF 2025

_STATE_ABBR = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA",
    "colorado": "CO", "connecticut": "CT", "delaware": "DE", "florida": "FL", "georgia": "GA",
    "hawaii": "HI", "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA",
    "kansas": "KS", "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS", "missouri": "MO",
    "montana": "MT", "nebraska": "NE", "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ",
    "new mexico": "NM", "new york": "NY", "north carolina": "NC", "north dakota": "ND", "ohio": "OH",
    "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT", "vermont": "VT",
    "virginia": "VA", "washington": "WA", "west virginia": "WV", "wisconsin": "WI",
    "district of columbia": "DC", "washington dc": "DC", "dc": "DC",
}


def normalize_state(state):
    """Accept 'California', 'CA', or 'ca' and return the 2-letter code."""
    s = state.strip()
    if len(s) == 2:
        return s.upper()
    return _STATE_ABBR.get(s.lower(), s.upper()[:2])


def parse_city_state(location_str):
    """'Austin, TX' -> ('Austin', 'TX'). Raises ValueError if unparseable."""
    parts = [p.strip() for p in location_str.split(",")]
    if len(parts) < 2:
        raise ValueError(f"Expected 'City, State' format, got: {location_str!r}")
    city, state = parts[0], parts[1]
    return city, normalize_state(state)


# ---------------------------------------------------------------------------
# Tier: Auto insurance (static dataset, no live source found)
# ---------------------------------------------------------------------------
_AUTO_INSURANCE_DATA = None


def _load_auto_insurance_table():
    global _AUTO_INSURANCE_DATA
    if _AUTO_INSURANCE_DATA is None:
        import json

        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state_auto_insurance_2026.json")
        with open(path) as f:
            _AUTO_INSURANCE_DATA = json.load(f)
    return _AUTO_INSURANCE_DATA


def get_auto_insurance_rate(state_abbr):
    """Static dataset only -- unlike state tax, I didn't find a source with
    a page structure clean/stable enough to build a live scraper against
    with confidence (auto insurance publishers mix multiple overlapping
    tables -- cheapest company, highest company, by age, by coverage type --
    on one page, making 'the' table harder to locate unambiguously than Tax
    Foundation's single rates table was). Static, sourced, dated instead;
    same staleness-awareness pattern as state tax could be added here later
    if this turns out to matter in practice."""
    table = _load_auto_insurance_table()
    rate = table["states"].get(state_abbr, table["national_average"])
    return rate, f"static_dataset_{table['last_updated']}"


# ---------------------------------------------------------------------------
# Tier: Federal + state income tax
# ---------------------------------------------------------------------------
_STATE_TAX_DATA = None


def _load_state_tax_table():
    global _STATE_TAX_DATA
    if _STATE_TAX_DATA is None:
        import json

        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state_tax_2026.json")
        with open(path) as f:
            _STATE_TAX_DATA = json.load(f)
    return _STATE_TAX_DATA


def check_state_tax_freshness():
    """Compute how stale the bundled state tax dataset is, relative to today.
    Returns (is_stale: bool, days_old: int, last_updated: str). Logs a
    one-time warning per process if stale -- this is a rolling check based
    on the file's own 'last_updated' field, so it self-maintains and never
    needs a code change; only the JSON's contents need refreshing."""
    global _stale_warning_logged
    table = _load_state_tax_table()
    last_updated_str = table["last_updated"]
    last_updated = datetime.strptime(last_updated_str, "%Y-%m-%d").date()
    days_old = (date.today() - last_updated).days
    is_stale = days_old > STATE_TAX_STALE_AFTER_DAYS

    if is_stale and not _stale_warning_logged:
        logger.warning(
            "State tax dataset (utils/state_tax_2026.json) is %d days old "
            "(last updated %s, source: %s). It may no longer reflect current "
            "state tax brackets. See COL_FEATURE_README.md for how to refresh it.",
            days_old, last_updated_str, table.get("source", "unknown"),
        )
        _stale_warning_logged = True

    return is_stale, days_old, last_updated_str


def _find_state_tax_table(soup):
    """Locate the rates table by nearby heading text rather than a hardcoded
    Tablepress id -- that id is specific to this year's table and will very
    likely change when Tax Foundation republishes next year."""
    for heading in soup.find_all(["h2", "h3", "h4"]):
        text = heading.get_text(strip=True).lower()
        if "income tax rates" in text and "bracket" in text:
            table = heading.find_next("table")
            if table:
                return table
    # Fallback: any table whose header row mentions both "State" and "Single Filer"
    for table in soup.find_all("table"):
        header_text = table.get_text(" ", strip=True)[:300].lower()
        if "state" in header_text and "single filer" in header_text:
            return table
    return None


def _parse_money(text):
    """'$3,000' -> 3000.0, '$100 credit' -> 100.0, 'n.a.' -> None"""
    if not text:
        return None
    m = re.search(r"\$?([\d,]+\.?\d*)", text)
    return float(m.group(1).replace(",", "")) if m else None


def _parse_rate(text):
    """'2.00%' -> 0.02, 'none' -> None (no-income-tax state)"""
    if not text or "none" in text.lower() or "n.a" in text.lower():
        return None
    m = re.search(r"([\d.]+)\s*%", text)
    return float(m.group(1)) / 100 if m else None


def parse_state_tax_table(table):
    """Given a BeautifulSoup <table> element in the format Tax Foundation
    uses (verified against the live page's rendered content, though the
    exact tag/class structure hasn't been directly inspected from this
    environment -- see COL_FEATURE_README.md), extract per-state brackets.

    Returns a dict of {state_abbr: {type, brackets, std_deduction}} or raises
    ValueError if the structure doesn't match what's expected, so the caller
    can fall back safely rather than silently trust a bad parse.
    """
    state_abbr_by_name = {v: v for v in _STATE_ABBR.values()}
    name_to_abbr = {k: v for k, v in _STATE_ABBR.items()}

    rows = table.find("tbody").find_all("tr") if table.find("tbody") else table.find_all("tr")[1:]

    states = {}
    current_state = None
    for tr in rows:
        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(cells) < 8:
            continue  # not a data row we understand -- skip rather than misparse

        label = cells[0]
        is_continuation = label.startswith("-")
        clean_name = re.sub(r"^-\s*", "", label)
        clean_name = re.sub(r"\s*\([a-z, ]+\)\s*$", "", clean_name, flags=re.I).strip()

        if is_continuation:
            if current_state is None:
                continue  # malformed / unexpected order -- skip
            state_name = current_state
        else:
            state_name = clean_name
            current_state = state_name

        abbr = name_to_abbr.get(state_name.lower())
        if abbr is None:
            continue  # unrecognized label (e.g. a footnote row) -- skip

        rate = _parse_rate(cells[1])
        floor = _parse_money(cells[3]) if len(cells) > 3 else None
        std_ded = _parse_money(cells[7]) if len(cells) > 7 else None

        if abbr not in states:
            states[abbr] = {"type": "none", "brackets": [], "std_deduction": std_ded or 0}

        if rate is not None:
            states[abbr]["brackets"].append([floor or 0, rate])
            states[abbr]["type"] = "graduated" if len(states[abbr]["brackets"]) > 1 else "flat"
        if std_ded:
            states[abbr]["std_deduction"] = std_ded

    # --- Validation: never trust a parse that looks structurally wrong ---
    if len(states) < 45:  # expect 50 states + DC; allow a few misses, not most
        raise ValueError(f"Only parsed {len(states)} states/territories, expected ~51")
    for abbr, data in states.items():
        for floor, rate in data["brackets"]:
            if not (0 <= rate <= 0.20):  # sanity bound -- no US state rate is remotely near this
                raise ValueError(f"Implausible rate {rate} for {abbr}, aborting parse")

    return states


def get_state_tax_brackets_live(source_url="https://taxfoundation.org/data/all/state/state-income-tax-rates-2026/"):
    """Live tier: scrape Tax Foundation's current rates page. Cached for 300
    days once successful (this data changes at most once a year). Returns
    None on any failure -- caller falls back to cache_stale, then the bundled
    static JSON, per the existing reliability pattern.

    Negative-cached for 1 hour on failure: without this, every request that
    hits a scrape failure (e.g. site down, layout changed, blocked) would
    retry the live HTTP call on every single invocation -- including, for
    the salary solver below, ~60 times in one bisection loop. A short
    negative-cache window keeps failures cheap and fast while still
    retrying periodically instead of giving up forever.
    """
    cache_key = "state_tax_live"
    failure_key = "state_tax_live:recent_failure"

    cached = cache_get(cache_key, max_age_days=300)
    if cached:
        return cached, "cache_fresh"

    if cache_get(failure_key, max_age_days=1 / 24):
        return None, None  # recent failure, skip straight to caller's fallback chain

    try:
        resp = requests.get(source_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        resp.raise_for_status()
        soup_module = __import__("bs4").BeautifulSoup
        soup = soup_module(resp.text, "lxml")
        table = _find_state_tax_table(soup)
        if table is None:
            raise ValueError("Could not locate the state tax rates table on the page")
        states = parse_state_tax_table(table)
        result = {
            "last_updated": date.today().isoformat(),
            "source": source_url,
            "states": states,
        }
        cache_set(cache_key, result)
        return result, "live"
    except Exception as e:
        logger.warning("Live state tax scrape failed (falling back to cache/static): %s", e)
        cache_set(failure_key, True)

    stale = cache_get_stale(cache_key)
    if stale:
        return stale, "cache_stale"

    return None, None


def get_state_tax_brackets(state_abbr):
    """Tries live scrape -> cache -> the bundled static dataset, in that
    order (see get_state_tax_brackets_live's docstring). The static JSON is
    now genuinely a last-resort fallback, not the primary source -- though
    it's the tier most likely to actually get hit in practice, since the
    live scrape depends on Tax Foundation's page structure staying stable,
    which wasn't something verifiable from the sandboxed environment this
    was built in. Treat 'live'/'cache_*' quality tags as the signal that
    the scraper is working; if you only ever see 'static_dataset_*', the
    scraper needs attention -- check logs for the warning it emits."""
    live_data, live_quality = get_state_tax_brackets_live()
    if live_data and state_abbr in live_data["states"]:
        return live_data["states"][state_abbr], live_quality

    # Fall back to the bundled static dataset
    table = _load_state_tax_table()
    is_stale, days_old, last_updated_str = check_state_tax_freshness()

    entry = table["states"].get(state_abbr)
    if entry is None:
        logger.warning("No state tax data for %s, treating as 0%%", state_abbr)
        entry = {"type": "none", "brackets": [], "std_deduction": 0}

    quality = f"static_dataset_{last_updated_str}"
    if is_stale:
        quality += f" (STALE: {days_old}d old, refresh needed)"
    return entry, quality


def _progressive_tax(taxable_income, brackets):
    """brackets: list of [floor, rate], each rate applies from that floor up
    to the next bracket's floor. Standard textbook marginal-bracket math."""
    if taxable_income <= 0 or not brackets:
        return 0.0
    tax = 0.0
    for i, (floor, rate) in enumerate(brackets):
        if taxable_income <= floor:
            break
        ceiling = brackets[i + 1][0] if i + 1 < len(brackets) else float("inf")
        taxed_in_bracket = min(taxable_income, ceiling) - floor
        tax += taxed_in_bracket * rate
    return tax


def get_federal_tax_brackets(year=2026):
    """Live: API Ninjas /v2/incometax (federal is on the free tier; state is
    a premium field there, which is why state tax uses the static dataset
    below instead). Falls back to a small hardcoded 2026 single-filer table
    if no key is configured or the call fails. Negative-cached for 1 hour on
    failure -- see get_state_tax_brackets_live's docstring for why."""
    cache_key = f"fed_tax:{year}"
    failure_key = f"fed_tax:{year}:recent_failure"

    cached = cache_get(cache_key, max_age_days=90)
    if cached:
        return cached, "cache_fresh"

    if API_NINJAS_KEY and not cache_get(failure_key, max_age_days=1 / 24):
        try:
            resp = requests.get(
                "https://api.api-ninjas.com/v2/incometax",
                params={"country": "US", "year": year, "regions": "federal"},
                headers={"X-Api-Key": API_NINJAS_KEY},
                timeout=8,
            )
            resp.raise_for_status()
            data = resp.json()
            fed = data[0]["federal"] if isinstance(data, list) else data["federal"]
            brackets = sorted(
                [[b["min"], b["rate"]] for b in fed["single"]], key=lambda b: b[0]
            )
            result = {"brackets": brackets, "std_deduction": 16100}
            cache_set(cache_key, result)
            return result, "live"
        except Exception as e:
            logger.warning("API Ninjas federal tax lookup failed: %s", e)
            cache_set(failure_key, True)

    stale = cache_get_stale(cache_key)
    if stale:
        return stale, "cache_stale"

    # Conservative fallback: 2026 single-filer federal brackets (IRS Rev.
    # Proc. 2025-32, via Tax Foundation). Update annually.
    fallback = {
        "brackets": [
            [0, 0.10], [12400, 0.12], [50400, 0.22], [105475, 0.24],
            [201775, 0.32], [256225, 0.35], [640600, 0.37],
        ],
        "std_deduction": 16100,
    }
    return fallback, "estimated"


def calculate_income_tax(gross_annual, state_abbr):
    """Returns (federal_tax, state_tax, quality_notes_dict) for a single filer."""
    fed_data, fed_quality = get_federal_tax_brackets()
    taxable_fed = max(0, gross_annual - fed_data["std_deduction"])
    federal_tax = _progressive_tax(taxable_fed, fed_data["brackets"])

    state_data, state_quality = get_state_tax_brackets(state_abbr)
    taxable_state = max(0, gross_annual - state_data.get("std_deduction", 0))
    state_tax = _progressive_tax(taxable_state, state_data["brackets"])

    return federal_tax, state_tax, {"federal": fed_quality, "state": state_quality}


# ---------------------------------------------------------------------------
# Tier: Utility rates (OpenEI URDB)
# ---------------------------------------------------------------------------
def get_utility_rate(lat, lon):
    """Returns (cents_per_kwh, utility_name, quality)."""
    cache_key = f"utility:{round(lat, 2)}:{round(lon, 2)}"
    cached = cache_get(cache_key, max_age_days=30)
    if cached:
        return cached["rate"], cached["utility"], "cache_fresh"

    if OPENEI_API_KEY:
        try:
            resp = requests.get(
                "https://api.openei.org/utility_rates",
                params={
                    "version": 8,
                    "format": "json",
                    "api_key": OPENEI_API_KEY,
                    "lat": lat,
                    "lon": lon,
                    "sector": "Residential",
                    "detail": "minimal",
                    "limit": 5,
                },
                timeout=8,
            )
            resp.raise_for_status()
            items = resp.json().get("items", [])
            rates = [it.get("energyratestructure") for it in items if it.get("energyratestructure")]
            if items:
                # Approximate: take the first tier of the first residential rate found
                flat = None
                for it in items:
                    ers = it.get("energyratestructure")
                    if ers and ers[0] and "rate" in ers[0][0]:
                        flat = ers[0][0]["rate"] * 100  # $/kWh -> cents/kWh
                        break
                if flat:
                    result = {"rate": round(flat, 2), "utility": items[0].get("utility", "unknown")}
                    cache_set(cache_key, result)
                    return result["rate"], result["utility"], "live"
        except Exception as e:
            logger.warning("OpenEI lookup failed: %s", e)

    stale = cache_get_stale(cache_key)
    if stale:
        return stale["rate"], stale["utility"], "cache_stale"

    return (
        CONSERVATIVE_FALLBACK["electricity_cents_per_kwh"],
        "estimated (national avg)",
        "estimated",
    )


# ---------------------------------------------------------------------------
# Tier: Gas prices (EIA.gov)
# ---------------------------------------------------------------------------
def get_gas_price(state_abbr):
    cache_key = f"gas:{state_abbr}"
    cached = cache_get(cache_key, max_age_days=7)
    if cached is not None:
        return cached, "cache_fresh"

    if EIA_API_KEY:
        try:
            resp = requests.get(
                "https://api.eia.gov/v2/petroleum/pri/gnd/data/",
                params={
                    "api_key": EIA_API_KEY,
                    "frequency": "weekly",
                    "data[0]": "value",
                    "facets[duoarea][]": f"S{state_abbr}",
                    "sort[0][column]": "period",
                    "sort[0][direction]": "desc",
                    "length": 1,
                },
                timeout=8,
            )
            resp.raise_for_status()
            rows = resp.json()["response"]["data"]
            if rows:
                price = float(rows[0]["value"])
                cache_set(cache_key, price)
                return price, "live"
        except Exception as e:
            logger.warning("EIA gas price lookup failed: %s", e)

    stale = cache_get_stale(cache_key)
    if stale is not None:
        return stale, "cache_stale"

    return CONSERVATIVE_FALLBACK["gas_price_per_gallon"], "estimated"


# ---------------------------------------------------------------------------
# Shared: lat/lon -> county FIPS, via the Census Bureau's free keyless
# geocoder. Feeds both the HUD rent lookup and the BEA price-index lookup
# below, so it's cached long-lived (county boundaries essentially never
# change, unlike the rates/indexes we look up for that county).
# ---------------------------------------------------------------------------
def _get_county_fips(lat, lon):
    """Returns (state_fips, county_fips) 2-digit/3-digit strings, or (None, None)
    if the geocoder can't place the point (e.g. way outside the US)."""
    cache_key = f"countyfips:{round(lat, 3)}:{round(lon, 3)}"
    cached = cache_get(cache_key, max_age_days=3650)
    if cached is not None:
        return cached["state_fips"], cached["county_fips"]

    try:
        resp = requests.get(
            "https://geocoding.geo.census.gov/geocoder/geographies/coordinates",
            params={
                "x": lon,
                "y": lat,
                "benchmark": "Public_AR_Current",
                "vintage": "Current_Current",
                "layers": "Counties",
                "format": "json",
            },
            timeout=8,
        )
        resp.raise_for_status()
        counties = resp.json()["result"]["geographies"].get("Counties", [])
        if counties:
            state_fips = counties[0]["STATE"]
            county_fips = counties[0]["COUNTY"]
            cache_set(cache_key, {"state_fips": state_fips, "county_fips": county_fips})
            return state_fips, county_fips
    except Exception as e:
        logger.warning("Census geocoder lookup failed for (%s, %s): %s", lat, lon, e)

    return None, None


# ---------------------------------------------------------------------------
# Tier: Housing (HUD Fair Market Rents)
# ---------------------------------------------------------------------------
def get_hud_rent(lat, lon):
    """1-bedroom Fair Market Rent for the county containing (lat, lon).
    Free bearer token from https://www.huduser.gov/portal/dataset/fmr-api.html
    Full US county/metro coverage (unlike Numbeo, which only has a few
    hundred cities worldwide and no free API). Returns (rent, quality). The result
    constantly seem low for the cities.  $500 is currently added to each result to
    derive a more reasonable rent for the area."""
    if lat is None or lon is None:
        return None, "estimated"

    state_fips, county_fips = _get_county_fips(lat, lon)
    if state_fips is None:
        return None, "estimated"

    entity_id = f"{state_fips}{county_fips}99999"  # whole-county FMR entity id
    cache_key = f"hud_rent:{entity_id}"
    cached = cache_get(cache_key, max_age_days=180)
    if cached is not None:
        return cached, "cache_fresh"

    if HUD_FMR_API_TOKEN:
        try:
            resp = requests.get(
                f"https://www.huduser.gov/hudapi/public/fmr/data/{entity_id}",
                headers={"Authorization": f"Bearer {HUD_FMR_API_TOKEN}"},
                timeout=8,
            )
            resp.raise_for_status()
            basicdata = resp.json()["data"]["basicdata"]
            # Whole-county entity ids (ending "99999") always return the
            # dict form of basicdata, not the ZIP-level array form that
            # Small Area FMR metros return for bare CBSA codes.
            rent = float(basicdata["One-Bedroom"])
            cache_set(cache_key, rent)
            return rent, "live"
        except Exception as e:
            logger.warning("HUD FMR lookup failed for %s: %s", entity_id, e)

    stale = cache_get_stale(cache_key)
    if stale is not None:
        return stale, "cache_stale"

    return None, "estimated"


# ---------------------------------------------------------------------------
# Tier: Groceries/general cost-of-living index (BEA Regional Price Parities)
# ---------------------------------------------------------------------------
def get_bea_price_index(lat, lon):
    """State-level BEA Regional Price Parity, 'all items', 100 = national
    average. Free registered key from https://apps.bea.gov/API/signup/
    Stands in for Numbeo's Groceries Index (which required a paid API) --
    used the same way: scale CONSERVATIVE_FALLBACK's national grocery
    estimate by (index / 100). Returns (index, quality)."""
    state_fips, _county_fips = _get_county_fips(lat, lon)
    if state_fips is None:
        return 100.0, "estimated"

    cache_key = f"bea_rpp:{state_fips}"
    cached = cache_get(cache_key, max_age_days=180)
    if cached is not None:
        return cached, "cache_fresh"

    if BEA_API_KEY:
        try:
            resp = requests.get(
                "https://apps.bea.gov/api/data",
                params={
                    "UserID": BEA_API_KEY,
                    "method": "GetData",
                    "datasetname": "Regional",
                    "TableName": "SARPP",  # State Regional Price Parities
                    "LineCode": 1,  # 1 = All items
                    "GeoFips": f"{state_fips}000",
                    "Year": "LAST5",
                    "ResultFormat": "JSON",
                },
                timeout=8,
            )
            resp.raise_for_status()
            rows = resp.json()["BEAAPI"]["Results"]["Data"]
            if rows:
                latest = max(rows, key=lambda r: r["TimePeriod"])
                index = float(latest["DataValue"])
                cache_set(cache_key, index)
                return index, "live"
        except Exception as e:
            logger.warning("BEA RPP lookup failed for state_fips=%s: %s", state_fips, e)

    stale = cache_get_stale(cache_key)
    if stale is not None:
        return stale, "cache_stale"

    return 100.0, "estimated"  # 100 = national average, neutral fallback


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------
def _net_monthly_pay(gross_salary, state_abbr, k401_percent):
    """Pure math, no external calls (tax bracket lookups hit the cache).
    Split out from calculate_takehome_and_expenses so the salary solver
    below can call this in a tight loop without re-fetching location data
    on every iteration -- location expenses don't depend on salary at all."""
    k401_frac = max(0, min(25, float(k401_percent))) / 100.0
    k401_contribution = gross_salary * k401_frac
    taxable_income = gross_salary - k401_contribution

    federal_tax, state_tax, tax_quality = calculate_income_tax(taxable_income, state_abbr)
    fica_tax = taxable_income * FICA_RATE

    annual_net = taxable_income - federal_tax - state_tax - fica_tax
    return annual_net / 12, k401_contribution, tax_quality


def _get_location_expenses(city, state_abbr):
    """Salary-independent fixed monthly expenses for a location: rent,
    electricity, gas, groceries, transport/insurance estimate. Returns
    (expenses_dict, monthly_total, quality_dict)."""
    try:
        lat, lon = get_lat_lon(city, state_abbr, logger=lambda *a: None)
        geo_quality = "live"
    except Exception as e:
        logger.warning("Geocoding failed for %s, %s: %s", city, state_abbr, e)
        lat, lon = None, None
        geo_quality = "failed"

    hud_rent, rent_quality = get_hud_rent(lat, lon)
    monthly_rent = (hud_rent + 550.0) if hud_rent is not None else CONSERVATIVE_FALLBACK["monthly_rent_1br"]

    price_index, price_index_quality = get_bea_price_index(lat, lon)
    monthly_groceries = CONSERVATIVE_FALLBACK["monthly_groceries"] * (price_index / 100)

    if lat is not None:
        kwh_rate_cents, utility_name, utility_quality = get_utility_rate(lat, lon)
    else:
        kwh_rate_cents, utility_name, utility_quality = (
            CONSERVATIVE_FALLBACK["electricity_cents_per_kwh"], "estimated", "estimated",
        )
    monthly_electric = (kwh_rate_cents / 100) * CONSERVATIVE_FALLBACK["monthly_kwh_usage"]

    gas_price, gas_quality = get_gas_price(state_abbr)
    monthly_gas = (1000 / 25) * gas_price  # ~1,000 mi/mo at 25 mpg, national-average proxy

    monthly_registration_misc = CONSERVATIVE_FALLBACK["monthly_registration_misc"]
    auto_insurance, auto_insurance_quality = get_auto_insurance_rate(state_abbr)
    health_insurance = HEALTH_INSURANCE_MONTHLY_EMPLOYEE_SHARE  # national average, not location-varying -- see constant's docstring

    expenses = {
        "housing_rent": round(monthly_rent, 2),
        "electricity": round(monthly_electric, 2),
        "gas": round(monthly_gas, 2),
        "groceries": round(monthly_groceries, 2),
        "auto_insurance": round(auto_insurance, 2),
        "registration_misc": round(monthly_registration_misc, 2),
        "health_insurance": round(health_insurance, 2),
    }
    monthly_total = sum(expenses.values())
    quality = {
        "geocoding": geo_quality,
        "utility_rate": utility_quality,
        "utility_name": utility_name,
        "gas_price": gas_quality,
        "housing_rent": rent_quality,
        "groceries_index": price_index_quality,
        "auto_insurance": auto_insurance_quality,
        "health_insurance": "estimated (national average, not location-varying)",
    }
    return expenses, monthly_total, quality


def _state_tax_warnings():
    warnings = []
    is_stale, days_old, last_updated_str = check_state_tax_freshness()
    if is_stale:
        warnings.append(
            f"State tax data was last updated {last_updated_str} ({days_old} days ago) "
            f"and may be out of date. See COL_FEATURE_README.md to refresh it."
        )
    return warnings


def calculate_takehome_and_expenses(gross_salary, location_str, k401_percent=10):
    """Main entry point for a single location + known salary. Returns a dict
    with net pay, expense breakdown, disposable cash, and a data_quality
    report so the UI can flag estimates."""
    city, state_abbr = parse_city_state(location_str)
    monthly_net, k401_contribution, tax_quality = _net_monthly_pay(gross_salary, state_abbr, k401_percent)
    expenses, monthly_expenses, expense_quality = _get_location_expenses(city, state_abbr)
    disposable_monthly = monthly_net - monthly_expenses

    return {
        "city": city,
        "state": state_abbr,
        "gross_annual": round(gross_salary, 2),
        "k401_contribution_annual": round(k401_contribution, 2),
        "net_monthly": round(monthly_net, 2),
        "expenses": expenses,
        "monthly_expenses_total": round(monthly_expenses, 2),
        "disposable_monthly": round(disposable_monthly, 2),
        "data_quality": {
            "federal_tax": tax_quality["federal"],
            "state_tax": tax_quality["state"],
            **expense_quality,
        },
        "excluded_from_model": [
            "local/municipal income tax", "401(k) employer match",
            "mortgage/buy scenario",
            "health insurance is a national-average estimate (not location-varying, not your actual plan)",
            "auto insurance is a state average (not personalized to age/vehicle/driving record)",
        ],
        "warnings": _state_tax_warnings(),
    }


def solve_required_salary(target_disposable_monthly, state_abbr, k401_percent, monthly_expenses_total,
                           lo=0.0, hi=5_000_000.0, tolerance=1.0, max_iterations=60):
    """Bisection search for the gross annual salary that produces
    target_disposable_monthly at a location with the given fixed monthly
    expenses. Net pay is monotonically increasing in gross salary (every
    marginal tax rate modeled here is well under 100%), so bisection is
    safe and converges in well under max_iterations for any realistic salary
    range -- 60 iterations over a $0-$5M bound gets well past cent precision.
    """
    for _ in range(max_iterations):
        mid = (lo + hi) / 2
        net_monthly, _, _ = _net_monthly_pay(mid, state_abbr, k401_percent)
        disposable = net_monthly - monthly_expenses_total
        if disposable < target_disposable_monthly:
            lo = mid
        else:
            hi = mid
        if hi - lo < tolerance:
            break
    return round(hi, 2)


def calculate_equivalent_salary(from_salary, from_location, to_location, k401_percent=10):
    """The 'what do I need to earn in the new city to keep my current
    lifestyle' calculation. Computes the From side normally, then solves
    (not guesses) for the To-side salary that reproduces the same monthly
    disposable cash, given To's actual location expenses.

    Returns (current_result, target_result) in the same shape as
    calculate_takehome_and_expenses, so existing callers/rendering code
    don't need to branch on which mode was used. target_result's
    gross_annual IS the solved answer, not a user-supplied guess.
    """
    current = calculate_takehome_and_expenses(from_salary, from_location, k401_percent)

    to_city, to_state_abbr = parse_city_state(to_location)
    to_expenses, to_monthly_expenses, to_expense_quality = _get_location_expenses(to_city, to_state_abbr)

    required_salary = solve_required_salary(
        current["disposable_monthly"], to_state_abbr, k401_percent, to_monthly_expenses
    )

    # Compute the full result at the solved salary so the numbers are
    # internally consistent (tax_quality, k401 contribution, etc. all
    # reflect the actual solved figure, not an approximation).
    target = calculate_takehome_and_expenses(required_salary, to_location, k401_percent)
    return current, target

