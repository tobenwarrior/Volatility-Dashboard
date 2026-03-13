"""
Postgres-backed history storage for IV snapshots.

Stores multi-tenor IV and risk reversal data every poll cycle.
Provides day-over-day change by comparing to the snapshot ~24 hours ago.
"""

import logging
import os
import math
from datetime import datetime, timezone, timedelta
from contextlib import contextmanager

import psycopg2
import psycopg2.pool

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL", "")


class HistoryStore:
    """Manages iv_snapshots table for historical day-over-day comparison."""

    def __init__(self, db_url=None):
        self._db_url = db_url or DATABASE_URL
        self._pool = psycopg2.pool.ThreadedConnectionPool(1, 5, self._db_url)
        self._ensure_db()
        self._cleanup_counter = 0

    @contextmanager
    def _connect(self):
        """Get a connection from the pool, auto-commit and return on exit."""
        conn = self._pool.getconn()
        try:
            conn.autocommit = True
            yield conn
        finally:
            self._pool.putconn(conn)

    def _ensure_db(self):
        """Create table and index if they don't exist, and migrate columns."""
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS iv_snapshots (
                        id SERIAL PRIMARY KEY,
                        timestamp TIMESTAMPTZ NOT NULL,
                        tenor TEXT NOT NULL,
                        atm_iv DOUBLE PRECISION,
                        rr_25d DOUBLE PRECISION,
                        currency TEXT NOT NULL DEFAULT 'BTC',
                        rv DOUBLE PRECISION
                    )
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_snapshots_currency_tenor_ts
                    ON iv_snapshots(currency, tenor, timestamp)
                """)
                # Migration: add rv column if table already existed without it
                cur.execute("""
                    ALTER TABLE iv_snapshots ADD COLUMN IF NOT EXISTS rv DOUBLE PRECISION
                """)

    def save_snapshot(self, timestamp, tenor_results, currency="BTC"):
        """Insert one row per tenor for the current poll cycle.

        Args:
            timestamp: ISO timestamp string.
            tenor_results: List of dicts with "label", "atm_iv", "rr_25d".
            currency: "BTC" or "ETH".
        """
        rows = [
            (timestamp, t["label"], t.get("atm_iv"), t.get("rr_25d"), currency, t.get("rv"))
            for t in tenor_results
        ]
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO iv_snapshots (timestamp, tenor, atm_iv, rr_25d, currency, rv) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    rows,
                )

        # Periodic cleanup (every ~60 saves ≈ once per hour at 60s intervals)
        self._cleanup_counter += 1
        if self._cleanup_counter >= 60:
            self._cleanup_counter = 0
            self.cleanup_old()

    def get_dod_changes(self, currency="BTC"):
        """Get changes for all tenors compared to the snapshot closest to 24h ago.

        Args:
            currency: "BTC" or "ETH".

        Returns:
            Dict mapping tenor label to {
                "dod_iv_change": float | None,
                "dod_rr_change": float | None,
                "change_hours": float | None,
            }.
        """
        now = datetime.now(timezone.utc)
        target = now - timedelta(hours=24)
        window_start = now - timedelta(hours=30)
        window_end = now - timedelta(hours=18)
        empty = {"dod_iv_change": None, "dod_rr_change": None, "change_hours": None}
        results = {}

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT DISTINCT tenor FROM iv_snapshots WHERE currency = %s",
                    (currency,),
                )
                tenors = [row[0] for row in cur.fetchall()]

                for tenor in tenors:
                    # Find the snapshot closest to 24h ago
                    cur.execute(
                        """
                        SELECT atm_iv, rr_25d, timestamp
                        FROM iv_snapshots
                        WHERE currency = %s AND tenor = %s
                          AND timestamp BETWEEN %s AND %s
                          AND atm_iv IS NOT NULL AND rr_25d IS NOT NULL
                        ORDER BY ABS(EXTRACT(EPOCH FROM (timestamp - %s)))
                        LIMIT 1
                        """,
                        (currency, tenor, window_start, window_end, target),
                    )
                    row = cur.fetchone()

                    # Fallback: oldest snapshot from the last 24h
                    if row is None:
                        cur.execute(
                            """
                            SELECT atm_iv, rr_25d, timestamp
                            FROM iv_snapshots
                            WHERE currency = %s AND tenor = %s AND timestamp >= %s
                              AND atm_iv IS NOT NULL AND rr_25d IS NOT NULL
                            ORDER BY timestamp ASC
                            LIMIT 1
                            """,
                            (currency, tenor, target),
                        )
                        row = cur.fetchone()

                    if row is None:
                        results[tenor] = dict(empty)
                        continue

                    old_iv, old_rr, old_ts = row
                    age_hours = (now - old_ts).total_seconds() / 3600

                    # Need at least 1 minute of history to be meaningful
                    if age_hours < 1 / 60:
                        results[tenor] = dict(empty)
                        continue

                    # Get the most recent snapshot
                    cur.execute(
                        """
                        SELECT atm_iv, rr_25d
                        FROM iv_snapshots
                        WHERE currency = %s AND tenor = %s
                        ORDER BY timestamp DESC
                        LIMIT 1
                        """,
                        (currency, tenor),
                    )
                    latest = cur.fetchone()

                    if latest is None:
                        results[tenor] = dict(empty)
                        continue

                    cur_iv, cur_rr = latest
                    dod_iv = (
                        (cur_iv - old_iv)
                        if cur_iv is not None and old_iv is not None
                        else None
                    )
                    dod_rr = (
                        (cur_rr - old_rr)
                        if cur_rr is not None and old_rr is not None
                        else None
                    )
                    results[tenor] = {
                        "dod_iv_change": dod_iv,
                        "dod_rr_change": dod_rr,
                        "change_hours": round(age_hours, 1),
                    }

        return results

    def get_history(self, tenor, hours, currency="BTC", max_points=350):
        """Query time-series data for a specific tenor.

        Args:
            tenor: Tenor label (e.g. "30D").
            hours: How many hours back to look.
            currency: "BTC" or "ETH".
            max_points: Max data points to return (uniform downsampling).

        Returns:
            List of dicts with "time" (unix epoch), "atm_iv", "rr_25d".
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT timestamp, atm_iv, rr_25d, rv FROM iv_snapshots "
                    "WHERE currency = %s AND tenor = %s AND timestamp >= %s "
                    "ORDER BY timestamp ASC",
                    (currency, tenor, cutoff),
                )
                rows = cur.fetchall()

        if not rows:
            return []

        # Uniform downsample if too many points, always keeping the last point
        if len(rows) > max_points:
            step = len(rows) / (max_points - 1)
            sampled = [rows[round(i * step)] for i in range(max_points - 1)]
            sampled.append(rows[-1])
            rows = sampled

        result = []
        for ts, atm_iv, rr_25d, rv in rows:
            unix_ts = int(ts.timestamp())
            result.append({
                "time": unix_ts,
                "atm_iv": round(atm_iv, 4) if atm_iv is not None else None,
                "rr_25d": round(rr_25d, 4) if rr_25d is not None else None,
                "rv": round(rv, 4) if rv is not None else None,
            })

        return result

    def get_vol_stats(self, hours=None, currency="BTC"):
        """Compute volatility statistics for each tenor from historical data.

        Args:
            hours: Lookback window in hours. None = all available data.
            currency: "BTC" or "ETH".

        Returns:
            List of dicts, one per tenor, with stats fields.
        """
        from config import TENORS

        tenor_order = {t["label"]: i for i, t in enumerate(TENORS)}

        now = datetime.now(timezone.utc)
        cutoff = None
        if hours is not None:
            cutoff = now - timedelta(hours=hours)

        results = []

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT DISTINCT tenor FROM iv_snapshots WHERE currency = %s",
                    (currency,),
                )
                tenors = [row[0] for row in cur.fetchall()]
                tenors.sort(key=lambda t: tenor_order.get(t, 999))

                for tenor in tenors:
                    if cutoff:
                        cur.execute(
                            "SELECT atm_iv, timestamp FROM iv_snapshots "
                            "WHERE currency = %s AND tenor = %s AND atm_iv IS NOT NULL "
                            "AND timestamp >= %s ORDER BY timestamp ASC",
                            (currency, tenor, cutoff),
                        )
                    else:
                        cur.execute(
                            "SELECT atm_iv, timestamp FROM iv_snapshots "
                            "WHERE currency = %s AND tenor = %s AND atm_iv IS NOT NULL "
                            "ORDER BY timestamp ASC",
                            (currency, tenor),
                        )
                    rows = cur.fetchall()

                    if not rows:
                        results.append({
                            "label": tenor,
                            "current_iv": None,
                            "iv_high": None, "iv_low": None,
                            "iv_percentile": None, "iv_zscore": None,
                            "samples": 0, "lookback_hours": None,
                        })
                        continue

                    values = [r[0] for r in rows]
                    current_iv = values[-1]
                    n = len(values)

                    iv_high = max(values)
                    iv_low = min(values)
                    iv_mean = sum(values) / n
                    variance = sum((v - iv_mean) ** 2 for v in values) / n
                    iv_std = math.sqrt(variance) if variance > 0 else 0

                    # Percentile rank: proportion of historical values strictly less
                    # than current. Standard convention (TastyTrade, Market Chameleon).
                    count_lt = sum(1 for v in values if v < current_iv)
                    iv_percentile = round(count_lt / n * 100, 1)

                    # Z-score (population std dev — describes the observed window)
                    iv_zscore = round((current_iv - iv_mean) / iv_std, 2) if iv_std > 0 else None

                    # Lookback hours from oldest to now
                    oldest_ts = rows[0][1]
                    lookback_hours = round((now - oldest_ts).total_seconds() / 3600, 1)

                    results.append({
                        "label": tenor,
                        "current_iv": round(current_iv, 2),
                        "iv_high": round(iv_high, 2),
                        "iv_low": round(iv_low, 2),
                        "iv_percentile": iv_percentile,
                        "iv_zscore": iv_zscore,
                        "samples": n,
                        "lookback_hours": lookback_hours,
                    })

        return results

    def cleanup_old(self, keep_days=None):
        """Delete snapshots older than keep_days to prevent unbounded growth."""
        if keep_days is None:
            from config import HISTORY_KEEP_DAYS
            keep_days = HISTORY_KEEP_DAYS
        cutoff = datetime.now(timezone.utc) - timedelta(days=keep_days)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM iv_snapshots WHERE timestamp < %s", (cutoff,)
                )
                deleted = cur.rowcount
                if deleted:
                    logger.info("Cleaned up %d old IV snapshots", deleted)
