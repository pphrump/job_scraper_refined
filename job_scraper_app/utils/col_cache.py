"""
Lightweight persistent cache for the True Cost of Living feature.

Why SQLite instead of an in-memory dict (like climate_utils.LOCATION_CACHE)?
The Flask dev server runs with debug=True, which reloads the whole process on
every file save. An in-memory cache gets wiped on every reload, which defeats
the point of caching against rate-limited free APIs (API Ninjas, OpenEI).
SQLite survives restarts with zero setup (one file, no server to run).

Usage:
    from utils.col_cache import cache_get, cache_get_stale, cache_set

    cached = cache_get("tax:federal:2026", max_age_days=90)
    if cached is None:
        cached = call_live_api(...)
        cache_set("tax:federal:2026", cached)
"""
import json
import os
import sqlite3
import time

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "col_cache.db"
)


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS col_cache (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            fetched_at REAL NOT NULL
        )
        """
    )
    return conn


def cache_get(key, max_age_days=None):
    """Return the cached value (parsed from JSON) if present and fresh enough.

    Returns None on a cache miss OR if the entry is older than max_age_days,
    so callers can fall through to a live API call. Use cache_get_stale() for
    the last-resort tier that ignores age.
    """
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT value, fetched_at FROM col_cache WHERE key = ?", (key,)
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return None

    value, fetched_at = row
    if max_age_days is not None:
        age_days = (time.time() - fetched_at) / 86400
        if age_days > max_age_days:
            return None
    return json.loads(value)


def cache_get_stale(key):
    """Return the cached value regardless of age. Last-resort fallback tier
    for when a live API is down/rate-limited and even the TTL has expired --
    stale data beats no data for a cost-of-living estimate."""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT value FROM col_cache WHERE key = ?", (key,)
        ).fetchone()
    finally:
        conn.close()
    return json.loads(row[0]) if row else None


def cache_set(key, value):
    conn = _get_conn()
    try:
        conn.execute(
            """
            INSERT INTO col_cache (key, value, fetched_at) VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                fetched_at = excluded.fetched_at
            """,
            (key, json.dumps(value), time.time()),
        )
        conn.commit()
    finally:
        conn.close()
