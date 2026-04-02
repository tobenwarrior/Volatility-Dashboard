"""
Postgres-backed history storage for IV snapshots with in-memory cache.

All reads served from an in-memory cache (zero DB egress during normal
operation).  DB writes are batched — one flush every *db_write_every*
save_snapshot() calls (default 5 → every 5 min at 60 s polling).
On startup the cache is backfilled from PostgreSQL.
"""

import logging
import os
import math
import threading
from datetime import datetime, timezone, timedelta
from contextlib import contextmanager

import psycopg2
import psycopg2.pool

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL", "")


class HistoryStore:
    """Manages iv_snapshots with in-memory reads and batched DB writes."""

    def __init__(self, db_url=None, db_write_every=10):
        self._db_url = db_url or DATABASE_URL
        self._pool = psycopg2.pool.ThreadedConnectionPool(1, 5, self._db_url)
        self._ensure_db()
        self._cleanup_counter = 0

        # Batched DB writes
        self._db_write_every = db_write_every
        self._write_counter = 0
        self._pending_rows = []

        # In-memory cache: (currency, tenor) -> [(datetime, atm_iv, rr_25d, rv), ...]
        self._cache = {}
        self._cache_lock = threading.Lock()
        self._backfill_cache()

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
                cur.execute("""
                    ALTER TABLE iv_snapshots ADD COLUMN IF NOT EXISTS rv DOUBLE PRECISION
                """)

    # ------------------------------------------------------------------
    # Cache management
    # ------------------------------------------------------------------

    def _backfill_cache(self):
        """Load existing data from DB into memory on startup."""
        from config import HISTORY_KEEP_DAYS
        cutoff = datetime.now(timezone.utc) - timedelta(days=HISTORY_KEEP_DAYS)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT timestamp, tenor, atm_iv, rr_25d, currency, rv "
                    "FROM iv_snapshots WHERE timestamp >= %s ORDER BY timestamp ASC",
                    (cutoff,),
                )
                for ts, tenor, atm_iv, rr_25d, currency, rv in cur.fetchall():
                    key = (currency, tenor)
                    if key not in self._cache:
                        self._cache[key] = []
                    self._cache[key].append((ts, atm_iv, rr_25d, rv))

        total = sum(len(v) for v in self._cache.values())
        logger.info("Backfilled %d snapshots into memory cache", total)

    def _parse_ts(self, timestamp):
        """Normalise a timestamp (string or datetime) to a tz-aware datetime."""
        if isinstance(timestamp, str):
            ts = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        else:
            ts = timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def save_snapshot(self, timestamp, tenor_results, currency="BTC"):
        """Append to in-memory cache (always) and batch for periodic DB flush."""
        ts = self._parse_ts(timestamp)

        db_rows = []
        with self._cache_lock:
            for t in tenor_results:
                key = (currency, t["label"])
                if key not in self._cache:
                    self._cache[key] = []
                self._cache[key].append(
                    (ts, t.get("atm_iv"), t.get("rr_25d"), t.get("rv"))
                )
                db_rows.append(
                    (ts, t["label"], t.get("atm_iv"), t.get("rr_25d"), currency, t.get("rv"))
                )

        self._pending_rows.extend(db_rows)
        self._write_counter += 1

        if self._write_counter >= self._db_write_every:
            self._flush_to_db()
            self._write_counter = 0

        self._cleanup_counter += 1
        if self._cleanup_counter >= 60:
            self._cleanup_counter = 0
            self.cleanup_old()

    def _flush_to_db(self):
        """Write buffered rows to PostgreSQL."""
        if not self._pending_rows:
            return
        rows = self._pending_rows
        self._pending_rows = []
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.executemany(
                        "INSERT INTO iv_snapshots (timestamp, tenor, atm_iv, rr_25d, currency, rv) "
                        "VALUES (%s, %s, %s, %s, %s, %s)",
                        rows,
                    )
            logger.info("Flushed %d rows to database", len(rows))
        except Exception:
            logger.exception("DB flush failed, re-queuing %d rows", len(rows))
            self._pending_rows = rows + self._pending_rows

    # ------------------------------------------------------------------
    # Reads — all from in-memory cache, zero DB egress
    # ------------------------------------------------------------------

    def get_dod_changes(self, currency="BTC"):
        """Day-over-day changes from in-memory cache."""
        now = datetime.now(timezone.utc)
        target = now - timedelta(hours=24)
        window_start = now - timedelta(hours=30)
        window_end = now - timedelta(hours=18)
        empty = {"dod_iv_change": None, "dod_rr_change": None, "change_hours": None}
        results = {}

        # Snapshot the relevant cache entries under lock
        with self._cache_lock:
            tenor_snapshots = {
                tenor: list(self._cache[(cur, tenor)])
                for (cur, tenor) in self._cache
                if cur == currency
            }

        for tenor, snapshots in tenor_snapshots.items():
            if not snapshots:
                results[tenor] = dict(empty)
                continue

            # Find snapshot closest to 24h ago within 18-30h window
            best = None
            best_dist = float("inf")
            for ts, atm_iv, rr_25d, rv in snapshots:
                if atm_iv is None or rr_25d is None:
                    continue
                if window_start <= ts <= window_end:
                    dist = abs((ts - target).total_seconds())
                    if dist < best_dist:
                        best = (ts, atm_iv, rr_25d)
                        best_dist = dist

            # Fallback: oldest snapshot from the last 24h
            if best is None:
                for ts, atm_iv, rr_25d, rv in snapshots:
                    if ts >= target and atm_iv is not None and rr_25d is not None:
                        best = (ts, atm_iv, rr_25d)
                        break

            if best is None:
                results[tenor] = dict(empty)
                continue

            old_ts, old_iv, old_rr = best
            age_hours = (now - old_ts).total_seconds() / 3600
            if age_hours < 1 / 60:
                results[tenor] = dict(empty)
                continue

            # Most recent snapshot with data
            latest_iv = latest_rr = None
            for ts, atm_iv, rr_25d, rv in reversed(snapshots):
                if atm_iv is not None:
                    latest_iv, latest_rr = atm_iv, rr_25d
                    break

            if latest_iv is None:
                results[tenor] = dict(empty)
                continue

            dod_iv = (latest_iv - old_iv) if old_iv is not None else None
            dod_rr = (latest_rr - old_rr) if latest_rr is not None and old_rr is not None else None
            results[tenor] = {
                "dod_iv_change": dod_iv,
                "dod_rr_change": dod_rr,
                "change_hours": round(age_hours, 1),
            }

        return results

    def get_history(self, tenor, hours, currency="BTC", max_points=350):
        """Time-series data from in-memory cache."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        key = (currency, tenor)

        with self._cache_lock:
            snapshots = list(self._cache.get(key, []))

        rows = [(ts, iv, rr, rv) for ts, iv, rr, rv in snapshots if ts >= cutoff]
        if not rows:
            return []

        # Uniform downsample
        if len(rows) > max_points:
            step = len(rows) / (max_points - 1)
            sampled = [rows[round(i * step)] for i in range(max_points - 1)]
            sampled.append(rows[-1])
            rows = sampled

        return [
            {
                "time": int(ts.timestamp()),
                "atm_iv": round(atm_iv, 4) if atm_iv is not None else None,
                "rr_25d": round(rr_25d, 4) if rr_25d is not None else None,
                "rv": round(rv, 4) if rv is not None else None,
            }
            for ts, atm_iv, rr_25d, rv in rows
        ]

    def get_vol_stats(self, hours=None, currency="BTC"):
        """Volatility statistics from in-memory cache."""
        from config import TENORS

        tenor_order = {t["label"]: i for i, t in enumerate(TENORS)}
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=hours) if hours is not None else None

        # Snapshot relevant cache entries under lock
        with self._cache_lock:
            tenor_snapshots = {
                tenor: list(self._cache[(cur, tenor)])
                for (cur, tenor) in self._cache
                if cur == currency
            }

        tenors = sorted(tenor_snapshots, key=lambda t: tenor_order.get(t, 999))
        results = []

        for tenor in tenors:
            snapshots = tenor_snapshots[tenor]
            if cutoff:
                filtered = [(ts, iv) for ts, iv, rr, rv in snapshots
                            if iv is not None and ts >= cutoff]
            else:
                filtered = [(ts, iv) for ts, iv, rr, rv in snapshots
                            if iv is not None]

            if not filtered:
                results.append({
                    "label": tenor,
                    "current_iv": None,
                    "iv_high": None, "iv_low": None,
                    "iv_percentile": None, "iv_zscore": None,
                    "samples": 0, "lookback_hours": None,
                })
                continue

            values = [iv for _, iv in filtered]
            current_iv = values[-1]
            n = len(values)

            iv_high = max(values)
            iv_low = min(values)
            iv_mean = sum(values) / n
            variance = sum((v - iv_mean) ** 2 for v in values) / n
            iv_std = math.sqrt(variance) if variance > 0 else 0

            count_lt = sum(1 for v in values if v < current_iv)
            iv_percentile = round(count_lt / n * 100, 1)
            iv_zscore = round((current_iv - iv_mean) / iv_std, 2) if iv_std > 0 else None

            oldest_ts = filtered[0][0]
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

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def cleanup_old(self, keep_days=None):
        """Delete old snapshots from both cache and DB."""
        if keep_days is None:
            from config import HISTORY_KEEP_DAYS
            keep_days = HISTORY_KEEP_DAYS
        cutoff = datetime.now(timezone.utc) - timedelta(days=keep_days)

        # Trim cache
        with self._cache_lock:
            for key in self._cache:
                self._cache[key] = [e for e in self._cache[key] if e[0] >= cutoff]

        # Trim DB
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM iv_snapshots WHERE timestamp < %s", (cutoff,)
                )
                deleted = cur.rowcount
                if deleted:
                    logger.info("Cleaned up %d old IV snapshots", deleted)
