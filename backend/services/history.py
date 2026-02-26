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
        """Create database directory and table if they don't exist."""
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS iv_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    tenor TEXT NOT NULL,
                    atm_iv REAL,
                    rr_25d REAL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_snapshots_tenor_ts
                ON iv_snapshots(tenor, timestamp)
            """)

    def _connect(self):
        return sqlite3.connect(self._db_path, check_same_thread=False)

    def save_snapshot(self, timestamp, tenor_results):
        """Insert one row per tenor for the current poll cycle.

        Args:
            timestamp: ISO timestamp string.
            tenor_results: List of dicts with "label", "atm_iv", "rr_25d".
        """
        rows = [
            (timestamp, t["label"], t.get("atm_iv"), t.get("rr_25d"))
            for t in tenor_results
        ]
        with self._connect() as conn:
            conn.executemany(
                "INSERT INTO iv_snapshots (timestamp, tenor, atm_iv, rr_25d) "
                "VALUES (?, ?, ?, ?)",
                rows,
            )

        # Periodic cleanup (every ~720 saves ≈ once per hour at 5s intervals)
        self._cleanup_counter += 1
        if self._cleanup_counter >= 720:
            self._cleanup_counter = 0
            self.cleanup_old()

    def get_dod_changes(self):
        """Get changes for all tenors compared to historical data.

        Strategy: prefer snapshot closest to 24h ago. If no data in the
        22-26h window, fall back to the oldest available snapshot so that
        newly-started instances still show useful change data.

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
                    "SELECT DISTINCT tenor FROM iv_snapshots"
                ).fetchall()
            ]

            for tenor in tenors:
                # Try: snapshot closest to 24h ago
                row = conn.execute(
                    """
                    SELECT atm_iv, rr_25d, timestamp
                    FROM iv_snapshots
                    WHERE tenor = ?
                    ORDER BY ABS(julianday(timestamp) - julianday(?))
                    LIMIT 1
                    """,
                    (tenor, target),
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

                # If not in the ideal 22-26h window, fall back to oldest snapshot
                if age_hours < 22 or age_hours > 26:
                    oldest = conn.execute(
                        """
                        SELECT atm_iv, rr_25d, timestamp
                        FROM iv_snapshots
                        WHERE tenor = ?
                        ORDER BY timestamp ASC
                        LIMIT 1
                        """,
                        (tenor,),
                    ).fetchone()

                    if oldest is None:
                        results[tenor] = dict(empty)
                        continue

                    old_iv, old_rr, old_ts = oldest
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
                    WHERE tenor = ?
                    ORDER BY timestamp DESC
                    LIMIT 1
                    """,
                    (tenor,),
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

    def get_history(self, tenor, hours, max_points=350):
        """Query time-series data for a specific tenor.

        Args:
            tenor: Tenor label (e.g. "30D").
            hours: How many hours back to look.
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
                "WHERE tenor = ? AND timestamp >= ? ORDER BY timestamp ASC",
                (tenor, cutoff),
            ).fetchall()

        if not rows:
            return []

        # Uniform downsample if too many points
        if len(rows) > max_points:
            step = len(rows) / max_points
            rows = [rows[round(i * step)] for i in range(max_points)]

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
