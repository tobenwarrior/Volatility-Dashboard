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

    def __init__(self, db_url=None, db_write_every=2, save_interval_seconds=0):
        self._db_url = db_url or DATABASE_URL
        self._pool = psycopg2.pool.ThreadedConnectionPool(1, 5, self._db_url)
        self._ensure_db()
        self._cleanup_counter = 0

        # Batched DB writes
        self._db_write_every = db_write_every
        self._write_counter = 0
        self._pending_rows = []

        # Throttle cache+DB writes independent of poll cadence.
        # save_snapshot() is called every POLL_INTERVAL, but we only persist
        # once per save_interval_seconds — keeps 180d of history inside the
        # Supabase free tier while the live dashboard still refreshes every poll.
        self._save_interval = save_interval_seconds
        self._last_save_ts = {}  # currency -> datetime of last persisted sample

        # In-memory cache: (currency, tenor) -> [(datetime, atm_iv, rr_25d, rv, bf_25d), ...]
        self._cache = {}
        self._cache_lock = threading.Lock()
        self._backfill_cache()
        # Enforce retention promptly on startup as well as during periodic
        # writes, so Supabase never keeps stale rows longer than necessary
        # after restarts. Normal API reads still use the in-memory cache.
        self.cleanup_old()

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
                cur.execute("""
                    ALTER TABLE iv_snapshots ADD COLUMN IF NOT EXISTS bf_25d DOUBLE PRECISION
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
                    "SELECT timestamp, tenor, atm_iv, rr_25d, currency, rv, bf_25d "
                    "FROM iv_snapshots WHERE timestamp >= %s ORDER BY timestamp ASC",
                    (cutoff,),
                )
                for ts, tenor, atm_iv, rr_25d, currency, rv, bf_25d in cur.fetchall():
                    key = (currency, tenor)
                    if key not in self._cache:
                        self._cache[key] = []
                    self._cache[key].append((ts, atm_iv, rr_25d, rv, bf_25d))

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
        """Append to in-memory cache and batch for periodic DB flush.

        If save_interval_seconds was set, drops samples that arrive sooner
        than that interval (per-currency). The live dashboard is still fed
        from the poller's in-memory latest snapshot, which is independent
        of this cache.
        """
        ts = self._parse_ts(timestamp)

        # Skip incomplete samples where no tenor has 25Δ RR data. This is the
        # signature of the startup race: the first poll runs ~1s after the WS
        # subscribe() for ticker channels, so the 25Δ strikes haven't delivered
        # quotes yet. Persisting such a sample would poison the cache's "latest"
        # slot with rr_25d=None and break DoD computations until the next
        # throttle-allowed save (up to save_interval_seconds later).
        if not any(t.get("rr_25d") is not None for t in tenor_results):
            return

        db_rows = []
        with self._cache_lock:
            # Throttle under the same lock that guards the cache, so the
            # read-check-write on _last_save_ts is trivially safe even if
            # a future refactor adds more writer threads per currency.
            if self._save_interval > 0:
                last = self._last_save_ts.get(currency)
                if last is not None and (ts - last).total_seconds() < self._save_interval:
                    return
                self._last_save_ts[currency] = ts

            for t in tenor_results:
                key = (currency, t["label"])
                if key not in self._cache:
                    self._cache[key] = []
                self._cache[key].append(
                    (ts, t.get("atm_iv"), t.get("rr_25d"), t.get("rv"), t.get("bf_25d"))
                )
                db_rows.append(
                    (ts, t["label"], t.get("atm_iv"), t.get("rr_25d"), currency, t.get("rv"), t.get("bf_25d"))
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
                        "INSERT INTO iv_snapshots (timestamp, tenor, atm_iv, rr_25d, currency, rv, bf_25d) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                        rows,
                    )
            logger.info("Flushed %d rows to database", len(rows))
        except Exception:
            logger.exception("DB flush failed, re-queuing %d rows", len(rows))
            self._pending_rows = rows + self._pending_rows

    # ------------------------------------------------------------------
    # Reads — all from in-memory cache, zero DB egress
    # ------------------------------------------------------------------

    def _empty_change(self):
        return {
            "iv_change": None,
            "rr_change": None,
            "bf_change": None,
            "dod_iv_change": None,
            "dod_rr_change": None,
            "dod_bf_change": None,
            "change_hours": None,
        }

    def get_range_changes(self, hours=24.0, currency="BTC", latest_tenors=None):
        """Range-based IV/RR/Fly changes from the in-memory cache.

        This powers selectable top-panel ranges without adding frontend
        per-tenor history fetches or DB reads.  ``latest_tenors`` may be the
        live poller snapshot from /api/tenors, letting the displayed change use
        the freshest live values as the current side of the diff while the old
        side still comes from persisted history.
        """
        try:
            hours = float(hours)
        except (TypeError, ValueError):
            hours = 24.0
        hours = max(hours, 0.01)

        now_fn = getattr(self, "_now", None)
        now = now_fn() if now_fn else datetime.now(timezone.utc)
        target = now - timedelta(hours=hours)
        empty = self._empty_change()

        live_by_tenor = {}
        if latest_tenors:
            live_by_tenor = {t.get("label"): t for t in latest_tenors if t.get("label")}

        with self._cache_lock:
            tenor_snapshots = {
                tenor: list(self._cache[(cur, tenor)])
                for (cur, tenor) in self._cache
                if cur == currency
            }

        results = {}
        for tenor, snapshots in tenor_snapshots.items():
            valid = [s for s in snapshots if s[1] is not None]
            if not valid:
                results[tenor] = dict(empty)
                continue

            live = live_by_tenor.get(tenor)
            if live:
                latest_ts = now
                latest_iv = live.get("atm_iv")
                latest_rr = live.get("rr_25d")
                latest_bf = live.get("bf_25d")
            else:
                latest_ts, latest_iv, latest_rr, _rv, latest_bf = valid[-1]

            if latest_iv is None:
                results[tenor] = dict(empty)
                continue

            old_candidates = [s for s in valid if s[0] < latest_ts]
            if not old_candidates:
                results[tenor] = dict(empty)
                continue

            # Pick the snapshot closest to the requested target.  Ties prefer
            # the older point so a 4h request with 1h/7h samples resolves to 7h
            # rather than reusing a too-recent value.
            old_ts, old_iv, old_rr, _old_rv, old_bf = min(
                old_candidates,
                key=lambda s: (abs((s[0] - target).total_seconds()), -((now - s[0]).total_seconds())),
            )

            age_hours = (now - old_ts).total_seconds() / 3600
            if age_hours < 1 / 60:
                results[tenor] = dict(empty)
                continue

            iv_change = latest_iv - old_iv if old_iv is not None else None
            rr_change = latest_rr - old_rr if latest_rr is not None and old_rr is not None else None
            bf_change = latest_bf - old_bf if latest_bf is not None and old_bf is not None else None

            results[tenor] = {
                "iv_change": iv_change,
                "rr_change": rr_change,
                "bf_change": bf_change,
                # Backwards-compatible names consumed by current frontend.
                "dod_iv_change": iv_change,
                "dod_rr_change": rr_change,
                "dod_bf_change": bf_change,
                "change_hours": round(age_hours, 1),
            }

        return results

    def get_dod_changes(self, currency="BTC"):
        """Day-over-day changes from in-memory cache."""
        return self.get_range_changes(24.0, currency)

    def get_history(self, tenor, hours, currency="BTC", max_points=350):
        """Time-series data from in-memory cache."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        key = (currency, tenor)

        with self._cache_lock:
            snapshots = list(self._cache.get(key, []))

        rows = [(ts, iv, rr, rv, bf) for ts, iv, rr, rv, bf in snapshots if ts >= cutoff]
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
                "bf_25d": round(bf_25d, 4) if bf_25d is not None else None,
            }
            for ts, atm_iv, rr_25d, rv, bf_25d in rows
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
                filtered = [(ts, iv) for ts, iv, rr, rv, bf in snapshots
                            if iv is not None and ts >= cutoff]
            else:
                filtered = [(ts, iv) for ts, iv, rr, rv, bf in snapshots
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
