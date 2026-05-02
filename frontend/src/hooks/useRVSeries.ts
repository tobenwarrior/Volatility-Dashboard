"use client";

import { useState, useEffect, useCallback } from "react";
import { Asset, TenorLabel } from "@/types";
import { fetchBinanceCandlesPaginated, getBinanceSymbol, type Candle } from "@/lib/binance";
import { PERIODS_PER_YEAR, TENOR_DAYS } from "@/lib/rv";

export interface RVPoint {
  time: number;
  rv: number;
}

export function filterRVSeriesForRange(
  series: RVPoint[],
  hours: number,
  nowSec: number = Math.floor(Date.now() / 1000)
): RVPoint[] {
  const cutoff = nowSec - hours * 3600;
  const filtered = series.filter((p) => p.time >= cutoff);
  if (filtered.length > 0) return filtered;

  // Binance 1h candles only finalize once per hour. During the first ~2 hours
  // after a completed candle, a 1H chart can have fresh IV samples but no RV
  // point inside the strict window. Keep the latest completed RV point so the
  // chart can render a flat RV/carry overlay instead of disappearing.
  const latest = series[series.length - 1];
  if (latest && latest.time >= cutoff - 2 * 3600) return [latest];
  return [];
}

function computeRollingRV(candles: Candle[], tenorDays: number): RVPoint[] {
  const nReturns = tenorDays * 24;
  if (candles.length < nReturns + 2) return [];

  const closes = candles.map((c) => c.close);
  const times = candles.map((c) => c.time);

  const logReturns: number[] = [];
  for (let i = 1; i < closes.length; i++) {
    if (closes[i] > 0 && closes[i - 1] > 0) {
      logReturns.push(Math.log(closes[i] / closes[i - 1]));
    } else {
      logReturns.push(0);
    }
  }

  const results: RVPoint[] = [];
  for (let end = nReturns; end <= logReturns.length; end++) {
    const window = logReturns.slice(end - nReturns, end);
    const variance = window.reduce((a, r) => a + r * r, 0) / window.length;
    const rv = Math.sqrt(variance) * Math.sqrt(PERIODS_PER_YEAR) * 100;
    const hourTs = Math.floor(times[end] / 1000) - (Math.floor(times[end] / 1000) % 3600);
    results.push({ time: hourTs, rv: Math.round(rv * 10000) / 10000 });
  }

  return results;
}

export function useRVSeries(tenor: TenorLabel, asset: Asset, enabled: boolean, hours: number = 48) {
  const [data, setData] = useState<RVPoint[]>([]);

  const fetchRV = useCallback(async () => {
    if (!enabled) return;
    try {
      const symbol = getBinanceSymbol(asset);
      const tenorDays = TENOR_DAYS[tenor];
      // Always use hourly candles with sqrt(8760) — paginate for 60D+ tenors
      // Need: tenor window + view range so RV spans the full chart
      const needed = tenorDays * 24 + hours + 24;
      const candles = await fetchBinanceCandlesPaginated(symbol, needed);
      const series = computeRollingRV(candles, tenorDays);
      setData(filterRVSeriesForRange(series, hours));
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
    const id = setInterval(fetchRV, 300_000);
    return () => clearInterval(id);
  }, [fetchRV, enabled]);

  return data;
}
