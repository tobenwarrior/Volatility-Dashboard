# BTC 30-Day ATM Volatility Estimator

A real-time dashboard that calculates the **30-day constant maturity at-the-money (ATM) implied volatility** for Bitcoin, sourced from the Deribit options exchange.

## What This Does

Options traders and researchers need a single, clean number representing "what the market expects BTC volatility to be over the next 30 days." This tool produces that number by:

- Pulling live **inverse (coin-margined)** BTC option data from Deribit's public API
- Identifying the two expiries that bracket the 30-day mark
- Selecting the ATM strike at each expiry and averaging the put/call implied volatilities
- Interpolating on **total variance** (not raw IV) to correctly account for the square-root-of-time scaling — the same method used by the CBOE to compute VIX

The result is an annualized implied volatility percentage, updated every 5 seconds and displayed on a Next.js dashboard.

## Architecture

```
backend/    Python Flask — API + calculation engine (port 5000)
frontend/   Next.js — Dashboard UI (port 3000, proxies /api to backend)
```

## Quick Start

```bash
# Terminal 1 — Backend
cd backend
pip install -r requirements.txt
python app.py

# Terminal 2 — Frontend
cd frontend
npm install
npm run dev
```

Open http://localhost:3000 in your browser.

## API Endpoints

| Route | Description |
|-------|-------------|
| `GET /api/data` | JSON with latest volatility estimate |
| `GET /api/price` | JSON with latest BTC spot price |

## Example JSON Response

```json
{
  "timestamp": "2026-02-26T01:55:01Z",
  "spot_price": 68249.39,
  "near_term": {
    "days": 29.3,
    "iv": 48.93,
    "expiry": "2026-03-27",
    "strike": 68000.0
  },
  "next_term": {
    "days": 57.3,
    "iv": 48.15,
    "expiry": "2026-04-24",
    "strike": 68000.0
  },
  "estimated_30d_vol": 48.89,
  "method": "variance_interpolation"
}
```

## Requirements

- Python 3.9+
- Node.js 18+
- Internet access to reach `deribit.com`
- No API keys needed (uses public endpoints only)
