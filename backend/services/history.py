"""
SQLite-backed history storage for IV snapshots.

Stores multi-tenor IV and risk reversal data every poll cycle.
Provides day-over-day change by comparing to the snapshot ~24 hours ago.
"""

import sqlite3
import logging
import os
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)


class HistoryStore:
    """Manages iv_snapshots table for historical day-over-day comparison."""

    def __init__(self, db_path):
        self._db_path = db_path
        self._ensure_db()
        self._cleanup_counter = 0

    def _ensure_db(self):
        """Create database directory and table if they don't exist, and migrate schema."""
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=DELETE")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS iv_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    tenor TEXT NOT NULL,
                    atm_iv REAL,
                    rr_25d REAL,
                    currency TEXT NOT NULL DEFAULT 'BTC'
                )
            """)
            # Migrate: add currency column if missing (existing data tagged as BTC)
            columns = [
                row[1] for row in conn.execute("PRAGMA table_info(iv_snapshots)")
            ]
            if "currency" not in columns:
                conn.execute(
                    "ALTER TABLE iv_snapshots ADD COLUMN currency TEXT NOT NULL DEFAULT 'BTC'"
                )
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_snapshots_currency_tenor_ts
                ON iv_snapshots(currency, tenor, timestamp)
            """)

    def _connect(self):
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=DELETE")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def save_snapshot(self, timestamp, tenor_results, currency="BTC"):
        """Insert one row per tenor for the current poll cycle.

        Args:
            timestamp: ISO timestamp string.
            tenor_results: List of dicts with "label", "atm_iv", "rr_25d".
            currency: "BTC" or "ETH".
        """
        rows = [
            (timestamp, t["label"], t.get("atm_iv"), t.get("rr_25d"), currency)
            for t in tenor_results
        ]
        with self._connect() as conn:
            conn.executemany(
                "INSERT INTO iv_snapshots (timestamp, tenor, atm_iv, rr_25d, currency) "
                "VALUES (?, ?, ?, ?, ?)",
                rows,
            )

        # Periodic cleanup (every ~720 saves ≈ once per hour at 5s intervals)
        self._cleanup_counter += 1
        if self._cleanup_counter >= 720:
            self._cleanup_counter = 0
            self.cleanup_old()

    def get_dod_changes(self, currency="BTC"):
        """Get changes for all tenors compared to the snapshot closest to 24h ago.

        Strategy: always use the snapshot closest to 24h ago regardless of
        how far it is from the ideal 24h window. For newly started instances
        this means comparing to the oldest available snapshot and showing
        the actual age via change_hours.

        Args:
            currency: "BTC" or "ETH".

        Returns:
            Dict mapping tenor label to {
                "dod_iv_change": float | None,
                "dod_rr_change": float | None,
                "change_hours": float | None,  # age of comparison snapshot
            }.
        """
        now = datetime.now(timezone.utc)
        target = (now - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
        empty = {"dod_iv_change": None, "dod_rr_change": None, "change_hours": None}
        results = {}

        with self._connect() as conn:
            tenors = [
                row[0]
                for row in conn.execute(
                    "SELECT DISTINCT tenor FROM iv_snapshots WHERE currency = ?",
                    (currency,),
                ).fetchall()
            ]

            for tenor in tenors:
                # Find the snapshot closest to 24h ago using indexed range scan
                # Check a window around the target, expanding if needed
                row = conn.execute(
                    """
                    SELECT atm_iv, rr_25d, timestamp
                    FROM iv_snapshots
                    WHERE currency = ? AND tenor = ? AND timestamp BETWEEN ? AND ?
                    ORDER BY ABS(julianday(timestamp) - julianday(?))
                    LIMIT 1
                    """,
                    (
                        currency,
                        tenor,
                        (now - timedelta(hours=30)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        (now - timedelta(hours=18)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        target,
                    ),
                ).fetchone()

                # If no snapshot in the 18-30h window, use the oldest snapshot
                # from the last 24h (the start of recent continuous data)
                if row is None:
                    row = conn.execute(
                        """
                        SELECT atm_iv, rr_25d, timestamp
                        FROM iv_snapshots
                        WHERE currency = ? AND tenor = ? AND timestamp >= ?
                        ORDER BY timestamp ASC
                        LIMIT 1
                        """,
                        (
                            currency,
                            tenor,
                            target,
                        ),
                    ).fetchone()

                if row is None:
                    results[tenor] = dict(empty)
                    continue

                old_iv, old_rr, old_ts = row

                try:
                    old_dt = datetime.fromisoformat(
                        old_ts.replace("Z", "+00:00")
                    )
                    age_hours = (now - old_dt).total_seconds() / 3600
                except (ValueError, TypeError):
                    results[tenor] = dict(empty)
                    continue

                # Need at least 1 minute of history to be meaningful
                if age_hours < 1 / 60:
                    results[tenor] = dict(empty)
                    continue

                # Get the most recent snapshot
                latest = conn.execute(
                    """
                    SELECT atm_iv, rr_25d
                    FROM iv_snapshots
                    WHERE currency = ? AND tenor = ?
                    ORDER BY timestamp DESC
                    LIMIT 1
                    """,
                    (currency, tenor),
                ).fetchone()

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
        cutoff = (
            datetime.now(timezone.utc) - timedelta(hours=hours)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")

        with self._connect() as conn:
            rows = conn.execute(
                "SELECT timestamp, atm_iv, rr_25d FROM iv_snapshots "
                "WHERE currency = ? AND tenor = ? AND timestamp >= ? ORDER BY timestamp ASC",
                (currency, tenor, cutoff),
            ).fetchall()

        if not rows:
            return []

        # Uniform downsample if too many points, always keeping the last point
        if len(rows) > max_points:
            step = len(rows) / (max_points - 1)
            sampled = [rows[round(i * step)] for i in range(max_points - 1)]
            sampled.append(rows[-1])
            rows = sampled

        result = []
        for ts, atm_iv, rr_25d in rows:
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                unix_ts = int(dt.timestamp())
            except (ValueError, TypeError):
                continue
            result.append({
                "time": unix_ts,
                "atm_iv": round(atm_iv, 4) if atm_iv is not None else None,
                "rr_25d": round(rr_25d, 4) if rr_25d is not None else None,
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
        import math
        from config import TENORS

        tenor_order = {t["label"]: i for i, t in enumerate(TENORS)}

        now = datetime.now(timezone.utc)
        cutoff = None
        if hours is not None:
            cutoff = (now - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")

        results = []

        with self._connect() as conn:
            tenors = [
                row[0]
                for row in conn.execute(
                    "SELECT DISTINCT tenor FROM iv_snapshots WHERE currency = ?",
                    (currency,),
                ).fetchall()
            ]
            tenors.sort(key=lambda t: tenor_order.get(t, 999))

            for tenor in tenors:
                # Get historical values within the lookback window
                if cutoff:
                    rows = conn.execute(
                        "SELECT atm_iv, timestamp FROM iv_snapshots "
                        "WHERE currency = ? AND tenor = ? AND atm_iv IS NOT NULL AND timestamp >= ? "
                        "ORDER BY timestamp ASC",
                        (currency, tenor, cutoff),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT atm_iv, timestamp FROM iv_snapshots "
                        "WHERE currency = ? AND tenor = ? AND atm_iv IS NOT NULL "
                        "ORDER BY timestamp ASC",
                        (currency, tenor),
                    ).fetchall()

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
                current_iv = values[-1]  # most recent value in the window
                n = len(values)

                iv_high = max(values)
                iv_low = min(values)
                iv_mean = sum(values) / n
                variance = sum((v - iv_mean) ** 2 for v in values) / n
                iv_std = math.sqrt(variance) if variance > 0 else 0

                # Percentile rank: proportion of historical values strictly less
                # than current. This is the standard convention used by trading
                # platforms (TastyTrade, Market Chameleon, etc.)
                count_lt = sum(1 for v in values if v < current_iv)
                iv_percentile = round(count_lt / n * 100, 1)

                # Z-score (population std dev — describes the observed window)
                iv_zscore = round((current_iv - iv_mean) / iv_std, 2) if iv_std > 0 else None

                # Lookback hours from oldest to now
                try:
                    oldest_ts = rows[0][1]
                    oldest_dt = datetime.fromisoformat(oldest_ts.replace("Z", "+00:00"))
                    lookback_hours = round((now - oldest_dt).total_seconds() / 3600, 1)
                except (ValueError, TypeError):
                    lookback_hours = None

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
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=keep_days)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        with self._connect() as conn:
            deleted = conn.execute(
                "DELETE FROM iv_snapshots WHERE timestamp < ?", (cutoff,)
            ).rowcount
            if deleted:
                logger.info("Cleaned up %d old IV snapshots", deleted)
