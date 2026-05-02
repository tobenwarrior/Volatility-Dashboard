# Volatility Dashboard — Agent Handover

> Read this top-to-bottom before touching any code. It explains the full system: what each piece does, where it lives, how data flows, and how to deploy/debug. Written for an LLM agent picking up the project cold.

---

## 1. What this project is

A real-time crypto options volatility dashboard for BTC and ETH. A trader uses it to monitor:

- **ATM implied volatility** at 6 tenors (1W, 2W, 30D, 60D, 90D, 180D)
- **25Δ Risk Reversal** (smile skew, directional)
- **25Δ Butterfly** (smile curvature / kurtosis proxy)
- **Realized volatility** vs implied (IV–RV carry)
- **Day-over-day changes** for IV, skew, fly
- **Vol Compass**: 2D IV-percentile vs spot-percentile heatmap with historical markers
- **Term structure chart** (ATM IV across tenors with 24h change overlay)

Live URL: **https://volatility-dashboard-gray.vercel.app/** (Vercel-hosted frontend).

The trader's primary use case is **execution benchmarking** — comparing dashboard numbers against OTC quotes from market makers before lifting/hitting. Secondary use is regime monitoring and signal generation.

---

## 2. Stack at a glance

| Layer | Tech | Where it runs |
|---|---|---|
| Frontend | Next.js 16 (App Router) + React 19 + Tailwind 4 + lightweight-charts 5 | Vercel (auto-deploys on git push) |
| Backend API | Flask (development server) + Flask-CORS + psycopg2 | GCE VM (`vol-backend`) via systemd |
| Data feed | Deribit REST + WebSocket; Binance REST (1h candles for RV, blocked) | Backend process |
| Storage | Supabase Postgres (free tier, 500 MB / 5 GB egress) | Supabase cloud |
| Realized vol candles | Binance `fapi.binance.com/fapi/v1/klines` | **451 blocked from GCP IPs** (see Known Issues) |

Architecture:

```
                       ┌──────────────┐
                       │  Vercel CDN  │  (Next.js, static + SSR)
                       └──────┬───────┘
                              │  /api/* rewrite
                              ▼
                  ┌───────────────────────┐
                  │  GCE VM `vol-backend` │  (systemd → Flask :5000)
                  │  ─────────────────    │
                  │  • 2× Poller threads  │  (BTC, ETH)
                  │  • WebSocket client   │  (Deribit ticker stream)
                  │  • In-memory cache    │  (latest snapshot, history)
                  └────┬───────────┬──────┘
                       │           │
                       │ writes    │ REST polls
                       ▼           ▼
               ┌────────────┐  ┌──────────────┐
               │  Supabase  │  │    Deribit   │
               │  Postgres  │  │  REST + WS   │
               └────────────┘  └──────────────┘
```

---

## 3. Repository layout

```
Volatility-Dashboard/
├── backend/
│   ├── app.py                      # Entry point — wires deps, starts Flask
│   ├── config.py                   # All tunables (intervals, tenors, retention)
│   ├── api/
│   │   └── client.py               # DeribitClient — REST GET wrappers
│   ├── models/
│   │   └── option.py               # Dataclasses (TermInfo, VolatilityResult)
│   ├── services/
│   │   ├── parser.py               # Instrument name parsing (BTC-25APR25-100000-C)
│   │   ├── greeks.py               # Black-Scholes greeks (used elsewhere, not poll loop)
│   │   ├── volatility.py           # ATM IV variance interpolation per tenor
│   │   ├── risk_reversal.py        # 25Δ RR + raw 25Δ call/put IVs
│   │   ├── realized_vol.py         # Binance 1h candles → rolling RV
│   │   └── history.py              # In-memory cache + Postgres persistence
│   ├── ws/
│   │   ├── client.py               # Deribit WebSocket client (auto-reconnect)
│   │   ├── ticker_store.py         # Thread-safe ticker snapshot cache
│   │   └── subscription_manager.py # Maintains subscription set near 25Δ strikes
│   └── web/
│       ├── poller.py               # Poller thread — orchestrates per-asset poll cycle
│       └── server.py               # Flask routes (/api/tenors, /api/history, …)
├── frontend/
│   ├── next.config.ts              # /api/* → BACKEND_URL rewrite
│   ├── package.json
│   └── src/
│       ├── app/
│       │   ├── layout.tsx          # Root layout
│       │   ├── page.tsx            # Main dashboard (BTC + ETH side-by-side)
│       │   └── compass/page.tsx    # Standalone full-screen Vol Compass page
│       ├── components/
│       │   ├── TenorTable.tsx      # The 6-row IV term-structure table (with Fly tooltip)
│       │   ├── TermStructureChart.tsx
│       │   ├── VolCompass.tsx      # 2D heatmap (IV-percentile × spot-percentile)
│       │   ├── VolStats.tsx        # IV high/low/percentile/zscore by tenor
│       │   ├── IvChart.tsx         # Time-series chart (ATM IV / RR / RV / Fly toggles)
│       │   ├── PriceTicker.tsx     # Spot price with green/red flash on change
│       │   ├── AssetSelector.tsx   # BTC/ETH pill toggle
│       │   ├── TenorSelector.tsx   # 1W…180D pill row
│       │   ├── TimeRangeSelector.tsx
│       │   ├── LayoutMenu.tsx      # Section reorder menu
│       │   └── StatusBadge.tsx     # LIVE / STALE indicator
│       ├── hooks/
│       │   ├── useTenors.ts        # /api/tenors poll every 60s
│       │   ├── useAssetData.ts     # Convenience wrapper (price + tenors + history)
│       │   ├── usePrice.ts         # /api/price poll every 5s
│       │   ├── useHistory.ts       # /api/history time-series fetch
│       │   ├── useRVSeries.ts      # /api/rv-series fetch
│       │   ├── useVolStats.ts      # /api/vol-stats fetch
│       │   └── useCompassData.ts   # Computes Vol Compass markers from history+candles
│       ├── lib/
│       │   ├── binance.ts          # Binance candle fetch (browser-side, NOT blocked)
│       │   └── rv.ts               # Realized vol math (frontend computation)
│       └── types/index.ts          # Shared TS types (TenorData, HistoryPoint, etc.)
└── HANDOVER.md                     # this file
```

---

## 4. Backend deep dive

### 4.1 Process model

`backend/app.py` is the entry point. On startup it:

1. Creates shared singletons: `DeribitClient`, `VolatilityCalculator`, `TickerDataStore`, `DeribitWSClient`, `SubscriptionManager`, `RiskReversalCalculator`, `HistoryStore`, `RealizedVolCalculator`.
2. Starts the WebSocket client thread and subscribes to spot price index channels for BTC and ETH.
3. Spawns one `Poller` thread per asset (BTC, ETH).
4. Builds the Flask app and runs it on port `5000` (override via `PORT` env var).

There are 4 long-lived threads at runtime: 1 Flask main thread, 1 WebSocket client thread, 2 Poller threads. Plus the connection pool worker threads in psycopg2 (1–5).

### 4.2 The poll cycle (`backend/web/poller.py`)

Each Poller runs an infinite loop with `POLL_INTERVAL=60s`. Per cycle (per asset):

1. **Get spot** — prefer WebSocket (`<5s` stale), fall back to REST `/api/v2/public/get_index_price`.
2. **Get full option chain** — REST `/api/v2/public/get_book_summary_by_currency`.
3. **Compute ATM IV per tenor** (`services/volatility.py`):
   - Parse all options into `{expiry: {strike: {C: iv, P: iv}}}`.
   - For each tenor, find bracketing expiries.
   - Variance interpolation: `σ²·T` is linear in T, then `σ = √(v_target / T_target)`.
   - At each expiry, ATM IV is interpolated linearly between the two nearest strikes by inverse distance.
4. **Update WebSocket subscriptions** — `SubscriptionManager` keeps the ~110 ticker channels around the moving 25Δ strikes (strikes drift as spot moves).
5. **Compute 25Δ RR + raw call/put IVs** (`services/risk_reversal.py`):
   - For each bracketing expiry, scan all OTM puts and OTM calls for live deltas from `TickerDataStore`.
   - Find two strikes whose `|delta|` brackets `0.25`, linear-interpolate IV.
   - Linear-interpolate IV across two bracketing expiries to the target tenor.
6. **Compute Fly** in poller.py: `bf_25d = call_iv + put_iv - 2 * atm_iv` (trader premium convention; exactly 2× the half-sum convention).
7. **Compute realized volatility** (`services/realized_vol.py`) from Binance 1h candles. Currently failing with HTTP 451 on GCE — see Known Issues.
8. **Get DoD changes** from `HistoryStore.get_dod_changes()` (in-memory).
9. **Assemble per-tenor dict** with all fields → `tenor_list`.
10. **Save snapshot** via `HistoryStore.save_snapshot()` — appends to in-memory cache and (throttled) Postgres flush.
11. **Store latest** in poller's own `_latest_tenor_data` for fast `/api/tenors` reads.

### 4.3 Key services

#### `services/volatility.py`
- `build_expiry_data(options, now)` → `({datetime: {strike: {C, P}}}, {datetime: days})`
- `_interpolate_iv(spot, expiry_data, expiry_days, target_days)` — variance interpolation (the right way)
- `calculate_multi_tenor(spot, options, tenors)` → results for all 6 tenors plus shared `expiry_data`/`expiry_days` for RR reuse

#### `services/risk_reversal.py`
- Returns `{label: {rr_25d, put_25d_iv, call_25d_iv}}` per tenor.
- Two interpolations: **strike** (delta-based, line 140-156) and **expiry** (time-based, line 81-106).
- Reads delta + mark_iv from `TickerDataStore` (no API calls during compute).

#### `services/history.py`
- **In-memory cache** keyed by `(currency, tenor)` → list of `(ts, atm_iv, rr_25d, rv, bf_25d)` tuples.
- Reads (DoD, history, vol stats) **never hit the DB** — all served from memory. This is the zero-egress pattern.
- Writes are **throttled by `SAVE_INTERVAL` (300s)** to keep 180d of history under the 500 MB Supabase free-tier ceiling.
- Writes are **batched by `db_write_every` (default 2)** — flushes accumulated rows every 2 saves, so worst-case in-flight loss window is `2 × SAVE_INTERVAL = 10 min`.
- **Startup race guard** (line 141-142): drops snapshots where no tenor has `rr_25d` (the WS hasn't delivered ticker quotes yet on the first poll).
- **Backfill on boot** (line 91-109): reads last `HISTORY_KEEP_DAYS=180` of rows from Postgres into memory.
- `cleanup_old()` runs every ~60 saves, deletes rows older than `HISTORY_KEEP_DAYS` from both cache and DB.

#### `services/realized_vol.py`
- Pulls Binance 1h candles, computes log-return-based annualized RV per tenor.
- **Currently broken on production** — Binance returns `HTTP 451` to GCP egress IPs. The poller swallows the exception and continues; RV column is empty in the API response. Frontend has its own RV computation from browser-side Binance fetches (`frontend/src/lib/rv.ts`) which works because it runs on the user's machine. See Known Issues.

#### `services/parser.py`
- Parses Deribit instrument names: `BTC-25APR25-100000-C` → `(currency, expiry, strike, opt_type)`.
- `format_instrument_name(currency, expiry, strike, opt_type)` for the reverse direction.

#### `ws/client.py` + `ws/ticker_store.py` + `ws/subscription_manager.py`
- WebSocket maintains a streaming feed of `ticker.<instrument>.100ms` channels.
- `TickerDataStore` is a thread-safe dict mapping instrument name → latest ticker payload (delta, mark_iv, mark_price, …).
- `SubscriptionManager` keeps subscriptions to ~5 strikes per side near each tenor's estimated 25Δ. Updates as spot moves.
- Spot price comes from `deribit_price_index.btc_usd` / `eth_usd` channels (no instrument needed).

### 4.4 Flask API (`backend/web/server.py`)

| Route | Query params | Returns |
|---|---|---|
| `GET /api/tenors` | `currency=BTC\|ETH` | Latest snapshot — full per-tenor block from poller's in-memory cache |
| `GET /api/history` | `currency`, `tenor`, `hours` (default 48, max 744) | Time-series array of `{time, atm_iv, rr_25d, rv, bf_25d}` |
| `GET /api/rv-series` | `currency`, `tenor` | Rolling hourly RV from Binance candles (broken on prod) |
| `GET /api/vol-stats` | `currency`, `hours` (0 = all) | IV high/low/percentile/zscore per tenor |
| `GET /api/data` | `currency` | Backwards-compat shim — extracts 30D from `/api/tenors` |
| `GET /api/price` | `currency` | Latest spot price + age |

All endpoints are JSON. CORS is wide-open via Flask-CORS. No auth.

### 4.5 Configuration (`backend/config.py`)

Key constants — change here, redeploy:

```python
POLL_INTERVAL = 60       # full poll cadence (s)
PRICE_INTERVAL = 5       # spot poll cadence (WS-fed, no REST cost)
SAVE_INTERVAL = 300      # min seconds between persisted samples (DB throttle)
HISTORY_KEEP_DAYS = 180  # retention; trader-requested for Vol Compass

TARGET_DELTA = 0.25      # 25Δ for RR/Fly
TICKER_CANDIDATES_PER_SIDE = 5  # WS subscriptions per side near 25Δ

TENORS = [
    {"label": "1W",   "days": 7},
    {"label": "2W",   "days": 14},
    {"label": "30D",  "days": 30},
    {"label": "60D",  "days": 60},
    {"label": "90D",  "days": 90},
    {"label": "180D", "days": 180},
]
```

Capacity math behind the defaults: `60 polls/hr × 24 × 180 × 6 tenors × 2 currencies × ~150 bytes/row ÷ 5 (SAVE_INTERVAL throttle)` ≈ **19.5 MB at 180d steady state** — well under the 500 MB Supabase free tier.

---

## 5. Frontend deep dive

### 5.1 Routing & pages

- `app/page.tsx` — main dashboard. Renders BTC and ETH side-by-side, each with: TenorTable, TermStructureChart, VolStats, IvChart, VolCompass.
- `app/compass/page.tsx` — full-screen Vol Compass (no tables/charts), used for trading-floor displays.

### 5.2 Data fetching strategy

All hooks live in `src/hooks/`. They poll the backend on independent intervals:

| Hook | Endpoint | Interval | Notes |
|---|---|---|---|
| `useTenors(asset)` | `/api/tenors` | 60s | Drives TenorTable + TermStructureChart |
| `usePrice(asset)` | `/api/price` | 5s | Spot price ticker, has green/red flash on change |
| `useHistory(tenor, range, asset)` | `/api/history` | On selector change | Time-series for IvChart |
| `useRVSeries(asset, tenor)` | `/api/rv-series` | On selector change | Realized vol overlay |
| `useVolStats(asset, hours)` | `/api/vol-stats` | 60s | IV percentile/zscore stats |
| `useCompassData(...)` | Composite | 60s | Computes VolCompass markers from history + Binance candles |

**Note**: the frontend talks to **its own origin** at `/api/*`. `next.config.ts` rewrites `/api/:path*` → `${BACKEND_URL}/api/:path*`. In production `BACKEND_URL` is set to the GCE VM's public IP. In dev it defaults to `http://localhost:5000`.

### 5.3 Key components

#### `TenorTable.tsx`
Six-row table per asset: Tenor / ATM IV / IV Chg / 25Δ RR / Skew Chg / Fly / Norm RR. The 25Δ RR cell has a hover tooltip showing the raw Call IV, Put IV, RR, and Fly with formula reminders. Tooltip is `bg-black/90 backdrop-blur` positioned above the cell to avoid clipping on the last row.

#### `VolCompass.tsx`
2D scatter on a `IV-percentile × spot-percentile` plane. Quadrants:
- Top-left: low spot, high IV ("crisis low")
- Top-right: high spot, high IV ("euphoria/fear top")
- Bottom-left: low spot, low IV ("capitulation calm")
- Bottom-right: high spot, low IV ("complacency")

Markers: current (yellow), last week (blue), last month (gray). Tooltip on hover.

#### `IvChart.tsx`
Time-series line chart using `lightweight-charts`. Toggles between ATM IV, 25Δ RR, RV, and Fly. Resampled to ≤350 points by the backend regardless of lookback window.

#### `TermStructureChart.tsx`
Bar+line combo: ATM IV curve across tenors as a line, 24h IV change as bars (green up / red down).

### 5.4 Types (`src/types/index.ts`)

Source of truth for what the API returns. **If you change a backend response shape, update this file.**

```ts
export interface TenorData {
  label: string;
  target_days: number;
  atm_iv: number | null;
  rr_25d: number | null;
  bf_25d: number | null;
  rv: number | null;
  call_25d_iv: number | null;   // raw 25Δ call IV (for RR tooltip)
  put_25d_iv: number | null;    // raw 25Δ put IV  (for RR tooltip)
  dod_iv_change: number | null;
  dod_rr_change: number | null;
  dod_bf_change: number | null;
  change_hours: number | null;
  method: string | null;
  error: string | null;
}
```

---

## 6. Database schema

Single table, `iv_snapshots`, on Supabase Postgres:

```sql
CREATE TABLE iv_snapshots (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    tenor TEXT NOT NULL,           -- '1W', '2W', '30D', '60D', '90D', '180D'
    atm_iv DOUBLE PRECISION,
    rr_25d DOUBLE PRECISION,
    currency TEXT NOT NULL DEFAULT 'BTC',
    rv DOUBLE PRECISION,
    bf_25d DOUBLE PRECISION
);

CREATE INDEX idx_snapshots_currency_tenor_ts
    ON iv_snapshots(currency, tenor, timestamp);
```

Schema migrations are idempotent `ALTER TABLE ADD COLUMN IF NOT EXISTS` calls in `HistoryStore._ensure_db()` — safe to redeploy.

**Important**: the `call_25d_iv` and `put_25d_iv` fields appear in the API response but are **NOT stored in the DB**. They're pass-through fields used only for the frontend tooltip. Adding them to the DB would grow row size; the trader can still verify Fly mathematically from the live values.

---

## 7. Deployment

### 7.1 Frontend (Vercel)

Auto-deploys on every push to `main`. Project already linked to the GitHub repo. Environment variables:

| Variable | Value |
|---|---|
| `BACKEND_URL` | `http://<VM_PUBLIC_IP>:5000` |

To check build status: `vercel.com/<account>/volatility-dashboard-gray`. If `npm run build` fails locally, it will fail on Vercel — fix it before pushing.

### 7.2 Backend (GCE VM via systemd)

VM hostname: `vol-backend` (Debian 12, in `asia-southeast1` for low Deribit latency).

systemd service: `/etc/systemd/system/vol-backend.service`. Key env vars set there:

```ini
Environment=DATABASE_URL=postgresql://postgres.rodoncgzpkuzruneuwlu:<PASSWORD>@aws-1-ap-southeast-1.pooler.supabase.com:6543/postgres
Environment=PORT=5000
```

Standard ops:

```bash
# SSH in
gcloud compute ssh vol-backend --zone=asia-southeast1-a

# Pull latest code
cd ~/Volatility-Dashboard && git pull

# Restart service
sudo systemctl restart vol-backend

# Check status
sudo systemctl status vol-backend

# Tail logs
sudo journalctl -u vol-backend -f

# Last 100 lines, no pager
sudo journalctl -u vol-backend -n 100 --no-pager
```

Startup takes **~12 seconds** (systemd 11s + Flask init ~1s). The first poll fires ~1s after WS subscribe; the startup-race guard in `history.py` prevents that incomplete sample from poisoning the cache.

### 7.3 Database (Supabase)

- Project ref: `rodoncgzpkuzruneuwlu`
- Region: `aws-ap-southeast-1` (Singapore)
- Connection: pooled at port `6543` (transaction mode) — required for psycopg2 in long-running connections
- Free tier limits: 500 MB storage, 5 GB monthly egress
- Egress consumption: nearly zero in steady state (in-memory cache serves all reads); ~22 MB on each backend restart (full backfill query). Tolerates ~221 restarts/month before hitting 5 GB.

Direct SQL access via Supabase dashboard → SQL Editor.

---

## 8. Critical concepts (don't skip)

### 8.1 Variance interpolation for ATM IV

When a tenor target (say 30 days) sits between two listed expiries (28 DTE and 35 DTE), you cannot just linearly interpolate IV — IV doesn't sum linearly across time, **variance** does. The correct formula:

```
v = σ² × T   (variance × time = total variance)
v_target = v1 + (v2 - v1) × (T_target - T1) / (T2 - T1)
σ_target = √(v_target / T_target)
```

This is implemented in `services/volatility.py:103-122`. **Do not change to plain linear interpolation of IV** — it underestimates IV in contango and overestimates in backwardation.

For RR and Fly we use **plain linear interpolation of the IVs** (not variance) because the smile shape is approximately stable across adjacent expiries and RR/Fly are differences, not levels. Both conventions are standard.

### 8.2 25Δ butterfly formula

The dashboard uses the **trader-requested premium convention**:

```
Fly = 25Δ Call IV + 25Δ Put IV − 2 × ATM IV
```

This equals exactly 2× the half-sum convention `(C+P)/2 − ATM`. The project trader explicitly corrected the dashboard to use this premium convention; keep backend calculations, API history, table legend, and tooltip formula labels aligned.

### 8.3 In-memory cache + DB throttle

`HistoryStore` is the heart of the egress optimization:

- **All reads** (`get_dod_changes`, `get_history`, `get_vol_stats`) hit the in-memory cache. Zero DB egress in steady state.
- **Writes** are throttled (`SAVE_INTERVAL=300s`) and batched (`db_write_every=2` → flush every 10 min). Keeps 180d under 500 MB.
- **The poller's own `_latest_tenor_data`** is the source for `/api/tenors` — even more direct than `HistoryStore`.

If you add a new field that needs to persist (like adding RV to history), update **3 places**:
1. `_ensure_db()` migration
2. `_backfill_cache()` SELECT
3. `save_snapshot()` cache append + `db_rows.append()`
4. `_flush_to_db()` INSERT
5. `get_dod_changes()` / `get_history()` / `get_vol_stats()` return shape
6. Frontend types in `src/types/index.ts`

If a new field is **API-only** (like `call_25d_iv` / `put_25d_iv`), only update `poller.py` line 130-143 and the frontend types. Do NOT add to `history.py` — it would grow row size needlessly.

### 8.4 Threading model & concurrency

- Two Poller threads (one per asset) write to `HistoryStore` concurrently.
- The cache and `_pending_rows` are guarded by `_cache_lock`.
- Per-currency throttle (`_last_save_ts[currency]`) is also under `_cache_lock` (was a flagged race that turned out to be false-positive given current architecture, but defensive lock is in place).
- `psycopg2.pool.ThreadedConnectionPool(1, 5, ...)` handles concurrent DB connections.

### 8.5 WebSocket startup race

When the backend starts, the poller fires immediately, but the WS subscriber needs ~0.5–1s to deliver ticker quotes for newly-subscribed channels. The first poll therefore has `delta=None` for all 25Δ strikes → `rr_25d=None`, `bf_25d=None`. This sample is **not persisted** (`history.py:141-142`). Without the guard, this incomplete sample becomes the cache's "latest" entry and breaks DoD computations until the next throttled save — up to 5 minutes later.

---

## 9. Known issues / pre-existing tech debt

### 9.1 Binance HTTP 451 from GCP egress
- **Symptom**: `services/realized_vol.py` raises `requests.exceptions.HTTPError: 451 Client Error` for all candle fetches.
- **Cause**: Binance geoblocks GCP egress IPs.
- **Effect**: RV column on the dashboard is empty (shown as "—"). All other columns fine.
- **Fix path**: Swap to Deribit perpetual candles (free, no geoblock). The endpoint is `/api/v2/public/get_tradingview_chart_data`. Estimated work: 30 min in `realized_vol.py`.

### 9.2 Missing log line "Backfilled N snapshots"
- **Symptom**: The log line that should appear on startup is silent.
- **Cause**: `logging.basicConfig` runs **after** `HistoryStore.__init__` in `app.py`. The backfill log call uses the unconfigured root logger.
- **Fix**: Move `logging.basicConfig` to before any service instantiation, or convert to `logging.getLogger(__name__)` with module-level configuration. Cosmetic only.

### 9.3 Flask development server in production
- The backend runs Flask's built-in dev server, not gunicorn/uwsgi. This is fine for one trader, but won't scale beyond ~10 concurrent users.
- **Fix path**: Switch to `gunicorn -w 1 --threads 4 app:app`. Single worker is required because all state (cache, WS connections, pollers) is in-process.

### 9.4 Supabase password exposed in chat
- The DATABASE_URL with password was shared in support transcripts. Recommended to rotate via Supabase dashboard → Settings → Database → Reset password, then update the systemd service file.

### 9.5 No write authentication
- The Flask API has no auth. Anyone with the GCE IP can hit `/api/*` endpoints. Read-only and the data is public-ish (just IV math), but worth keeping in mind if you add admin endpoints.

---

## 10. Common operations

### 10.1 Add a new tenor (e.g., 365D)

1. Add to `config.TENORS`:
   ```python
   {"label": "365D", "days": 365}
   ```
2. Update frontend `TenorLabel` type in `src/types/index.ts`.
3. Update `TenorSelector.tsx` if you want it in the picker.
4. Update `HISTORY_KEEP_DAYS` if 365 > current value.
5. Bump `SAVE_INTERVAL` proportionally to stay under 500 MB. (1.16× rows for 7→8 tenors → ~22.6 MB, still fine.)
6. Restart backend.

### 10.2 Add a new column to the API response

If it's **derived from existing data** and doesn't need history:
- Edit `poller.py:130-143` to compute and include it in the tenor dict.
- Add to TypeScript types.
- Render in `TenorTable.tsx`.
- Done. No DB change.

If it's **a new historical metric** that needs DoD/percentiles:
- Follow §8.3 — touch all 6 places in `history.py` plus types and poller.

### 10.3 Lower poll frequency (e.g., to save egress)

`POLL_INTERVAL` is the main lever, but **the WS subscriptions are the real network cost**, not the REST polls. To genuinely reduce load:
- Increase `SAVE_INTERVAL` (DB writes) — biggest egress impact.
- Reduce `TICKER_CANDIDATES_PER_SIDE` from 5 → 3 (fewer WS channels).
- Increase `POLL_INTERVAL` — minimal egress impact, mostly CPU.

### 10.4 Local development

```bash
# Backend
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt   # (or read app.py imports)
export DATABASE_URL=postgresql://...   # use the same Supabase URL
export PORT=5001                       # 5000 conflicts with macOS AirPlay
python app.py

# Frontend (separate terminal)
cd frontend
npm install
BACKEND_URL=http://localhost:5001 npm run dev -- --port 3002
# Open http://localhost:3002
```

### 10.5 Inspecting the live DB

Supabase dashboard → SQL Editor:

```sql
-- Row count by currency
SELECT currency, COUNT(*) FROM iv_snapshots GROUP BY currency;

-- Latest snapshot per tenor
SELECT DISTINCT ON (currency, tenor) currency, tenor, timestamp, atm_iv, rr_25d, bf_25d
FROM iv_snapshots
ORDER BY currency, tenor, timestamp DESC;

-- Storage size
SELECT pg_size_pretty(pg_total_relation_size('iv_snapshots'));
```

---

## 11. Reading the trader's mind

The trader uses this dashboard for these workflows (in priority order):

1. **Execution benchmark** — "MM quoted me 0.30/0.35 on the 30D Fly. What's the dashboard showing?" If your number disagrees with the MM by more than the bid-ask, either your data is stale (check timestamps) or the MM is being aggressive.
2. **Cross-asset RV** — comparing BTC vs ETH on the same metric across tenors. The ETH/BTC Fly ratio at 90D and 180D is the most common screen check.
3. **Term-structure shape** — flat-or-inverted Fly term structures are unusual and signal-rich.
4. **Vol Compass regime check** — quadrant + IV percentile tells him whether to lean long or short vol.
5. **DoD changes** — IV Chg and Skew Chg columns are the morning glance for "what moved overnight."

When implementing new features, **always ask the trader** rather than assuming. Don't add toggles "for flexibility"; he'll tell you exactly what cut he wants.

---

## 12. What NOT to do

- **Don't switch the Fly formula back to `(C+P)/2 − ATM`** without explicit trader instruction — see §8.2.
- **Don't change ATM IV from variance interpolation to linear** — see §8.1.
- **Don't add the raw `call_25d_iv` / `put_25d_iv` to the DB schema** — they're tooltip-only.
- **Don't disable the startup-race guard in `history.py:141-142`** — it prevents poisoned cache state.
- **Don't run multiple backend workers** with the in-memory cache pattern — every worker would have its own cache and they'd diverge.
- **Don't push to Supabase free-tier limits** with new features without recomputing the storage/egress budget. The 180d × 6 tenors × 2 assets × throttled writes math is tight.
- **Don't add destructive cleanup beyond `cleanup_old`** — accidentally deleting historical IV data wipes the trader's ability to compute long-window percentiles.
- **Don't commit `DATABASE_URL`** with credentials. It's in the systemd service file, not the repo.

---

## 13. Quick verification after any deploy

After pushing changes:

1. **Frontend** — open the live URL, check both BTC and ETH panels render. Hover the 25Δ RR cell on BTC 30D → verify tooltip shows Call IV + Put IV + RR + Fly with no transparent background and no clipping.
2. **Backend** — `sudo systemctl status vol-backend` → `active (running)`, memory ~95 MB, recent logs show `Poll complete: 6/6 tenors computed` for both BTC and ETH.
3. **API sanity** — `curl http://<VM_IP>:5000/api/tenors?currency=BTC | jq '.tenors[0]'` should return a fully populated object with `atm_iv`, `rr_25d`, `bf_25d`, `call_25d_iv`, `put_25d_iv`, `dod_iv_change` all non-null (after 24h of uptime).
4. **DB write** — Supabase SQL editor: `SELECT MAX(timestamp) FROM iv_snapshots;` should be within `SAVE_INTERVAL` (5 min) of now.
5. **Sanity-check a Fly value** — pick any tenor in the dashboard, hover RR for the tooltip, verify `Call + Put − 2×ATM = Fly` to 2 decimal places.

If all 5 pass, the deploy is good.

---

## 14. Contact / escalation

- **Frontend deploys** — Vercel auto-deploys on `git push origin main`. No manual step.
- **Backend deploys** — `git pull && sudo systemctl restart vol-backend` on the GCE VM.
- **Database access** — Supabase dashboard, login with project owner's account.
- **Live data feed issues** — Deribit status page (`status.deribit.com`).

---

*Last updated for this handover. If you spot inaccuracies after a recent change, update this file rather than working around them.*
