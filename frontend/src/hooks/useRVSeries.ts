"use client";

import { useState, useEffect, useCallback } from "react";
import { Asset, TenorLabel } from "@/types";

export interface RVPoint {
  time: number;
  rv: number;
}

const BINANCE_SYMBOLS: Record<Asset, string> = {
  BTC: "BTCUSDT",
  ETH: "ETHUSDT",
};

const TENOR_DAYS: Record<TenorLabel, number> = {
  "1W": 7,
  "2W": 14,
  "30D": 30,
  "60D": 60,
  "90D": 90,
  "180D": 180,
};

const PERIODS_PER_YEAR = 8760; // hours in a year

function computeRollingRV(
  candles: { time: number; close: number }[],
  tenorDays: number
): RVPoint[] {
  const nReturns = tenorDays * 24;
  if (candles.length < nReturns + 2) return [];

  const closes = candles.map((c) => c.close);
  const times = candles.map((c) => c.time);

  // Compute log returns
  const logReturns: number[] = [];
  for (let i = 1; i < closes.length; i++) {
    if (closes[i] > 0 && closes[i - 1] > 0) {
      logReturns.push(Math.log(closes[i] / closes[i - 1]));
    } else {
      logReturns.push(0);
    }
  }

  // Rolling RV
  const results: RVPoint[] = [];
  for (let end = nReturns; end <= logReturns.length; end++) {
    const window = logReturns.slice(end - nReturns, end);
    const mean = window.reduce((a, b) => a + b, 0) / window.length;
    const variance =
      window.reduce((a, r) => a + (r - mean) ** 2, 0) / (window.length - 1);
    const rv = Math.sqrt(variance) * Math.sqrt(PERIODS_PER_YEAR) * 100;
    // Key by candle open time floored to hour (unix seconds)
    const hourTs = Math.floor(times[end] / 1000) - (Math.floor(times[end] / 1000) % 3600);
    results.push({ time: hourTs, rv: Math.round(rv * 10000) / 10000 });
  }

  return results;
}

async function fetchBinanceCandles(symbol: string): Promise<{ time: number; close: number }[]> {
  const res = await fetch(
    `https://fapi.binance.com/fapi/v1/klines?symbol=${symbol}&interval=1h&limit=1500`
  );
  if (!res.ok) return [];
  const raw: unknown[][] = await res.json();
  return raw.map((c) => ({
    time: c[0] as number, // open time in ms
    close: parseFloat(c[4] as string),
  }));
}

export function useRVSeries(tenor: TenorLabel, asset: Asset, enabled: boolean, hours: number = 48) {
  const [data, setData] = useState<RVPoint[]>([]);

  const fetchRV = useCallback(async () => {
    if (!enabled) return;
    try {
      const symbol = BINANCE_SYMBOLS[asset];
      const candles = await fetchBinanceCandles(symbol);
      const tenorDays = TENOR_DAYS[tenor];
      const series = computeRollingRV(candles, tenorDays);
      // Filter to match the selected time range
      const cutoff = Math.floor(Date.now() / 1000) - hours * 3600;
      setData(series.filter((p) => p.time >= cutoff));
    } catch {
      // silently ignore — RV is optional overlay
    }
  }, [tenor, asset, enabled, hours]);

  useEffect(() => {
    if (!enabled) {
      setData([]);
      return;
    }
    fetchRV();
    const id = setInterval(fetchRV, 300_000); // refresh every 5 min
    return () => clearInterval(id);
  }, [fetchRV, enabled]);

  return data;
}
