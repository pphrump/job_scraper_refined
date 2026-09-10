#!/usr/bin/env python3
"""
Check whether utils/state_tax_2026.json needs refreshing, without starting
the Flask app.

Usage:
    python3 check_state_tax_freshness.py

Exit code 0 if fresh, 1 if stale -- so this can be wired into a cron job or
CI check, e.g.:
    0 9 1 * * cd /path/to/jobs-scraper && python3 check_state_tax_freshness.py || mail -s "state tax data stale" you@example.com

Recommended low-effort refresh path: rather than writing a scraper against
Tax Foundation's page (whose HTML/XLSX layout isn't something we could
verify from a sandboxed environment when this was built), just paste this
script's output into a fresh conversation with Claude and ask it to
re-fetch current state tax brackets and regenerate the JSON -- that's a
five-minute task for a model with live web access, and far less fragile
than an unverified scraper running unattended.
"""
import sys

from utils.col_utils import check_state_tax_freshness

if __name__ == "__main__":
    is_stale, days_old, last_updated = check_state_tax_freshness()
    if is_stale:
        print(f"STALE: state tax data last updated {last_updated} ({days_old} days ago).")
        print("Refresh utils/state_tax_2026.json -- see COL_FEATURE_README.md.")
        sys.exit(1)
    else:
        print(f"OK: state tax data last updated {last_updated} ({days_old} days ago, within {365} day threshold).")
        sys.exit(0)
