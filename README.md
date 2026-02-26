# BTC Volatility Estimator

A real-time dashboard that calculates **multi-tenor ATM implied volatility** and **25-delta risk reversals** for Bitcoin, sourced from the Deribit options exchange.

## Prerequisites

- Python 3.9+
- Node.js 18+
- Internet access to reach `deribit.com`
- No API keys needed (uses public endpoints only)

## Setup & Installation

### 1. Clone the repository

```bash
git clone https://github.com/your-username/Volatility-Estimator.git
cd Volatility-Estimator
```

### 2. Backend

```bash
cd backend
pip install -r requirements.txt
```

### 3. Frontend

```bash
cd frontend
npm install
```

## Running

Open two terminals:

```bash
# Terminal 1 — Start the backend (port 5000)
cd backend
python app.py
```

```bash
# Terminal 2 — Start the frontend (port 3000)
cd frontend
npm run dev
```

Open http://localhost:3000 in your browser. Data begins populating immediately.

---

## What This Does

Options traders need a clean view of the vol surface — how implied volatility and skew behave across different time horizons. This tool provides that by:

- Pulling live **inverse (coin-margined)** BTC option data from Deribit's public API
- Computing **ATM IV** for 6 tenors (1W, 2W, 30D, 60D, 90D, 180D) using variance interpolation across expiries that bracket each target
- Computing **25-delta risk reversals** (call IV − put IV) by approximating Black-Scholes delta per strike, interpolating to find the 25-delta point on each side
- Tracking **day-over-day changes** in both IV and skew
- Storing history in SQLite and serving it via API for charting

Results update every 5 seconds and are displayed on a Next.js dashboard with interactive historical charts.

## Dashboard Features

- **Term structure table** — ATM IV, 25Δ RR, IV change, and skew change for all tenors
- **Historical chart** — ATM IV and 25Δ RR overlaid on a single chart with dual y-axes (left = IV%, right = RR)
- **Tenor selector** — Switch between 1W, 2W, 30D, 60D, 90D, 180D
- **Time range selector** — 1H, 4H, 24H, 7D views
- **Live BTC price** with color-coded changes

## Architecture

```
backend/    Python Flask — API + calculation engine (port 5000)
frontend/   Next.js — Dashboard UI (port 3000, proxies /api to backend)
```

### Key Backend Modules

| Module | Purpose |
|--------|---------|
| `services/volatility.py` | ATM IV computation with variance interpolation |
| `services/risk_reversal.py` | 25-delta RR with per-strike BS delta approximation |
| `services/history.py` | SQLite storage + downsampled history queries |
| `web/server.py` | Flask API endpoints |

## API Endpoints

| Route | Description |
|-------|-------------|
| `GET /api/tenors` | All tenor data (IV, RR, changes) |
| `GET /api/history?tenor=30D&hours=24` | Historical IV + RR for charting |
| `GET /api/price` | Latest BTC spot price |
| `GET /api/data` | Legacy — 30D volatility estimate |

## Technical Details

- **Variance interpolation** for ATM IV across expiries (same method as CBOE VIX)
- **Linear interpolation** for RR spreads between bracketing deltas
- **Delta approximation** uses Black-Scholes with convexity adjustment: `d1 = (ln(S/K) + 0.5σ²T) / (σ√T)`
- **Batch expansion** for delta search — starts with 5 closest strikes, expands until 0.25 delta is bracketed
- History stored every 5 seconds, retained for 14 days, downsampled to 350 points max for API responses

