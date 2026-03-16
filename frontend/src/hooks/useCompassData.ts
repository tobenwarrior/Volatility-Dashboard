"use client";

import { useState, useEffect, useCallback } from "react";
import { Asset, TenorLabel, TimeRange, TIME_RANGE_HOURS } from "@/types";
import { fetchBinanceCandles, fetchBinanceCandlesPaginated, getBinanceSymbol } from "@/lib/binance";
import { computeCurrentRV, TENOR_DAYS } from "@/lib/rv";

export interface CompassMarker {
  spotPct: number;  // 0–100: spot percentile in range (high = bearish = right)
  ivPct: number;    // 0–100: IV percentile in range (high = top = sell vol)
}

export interface CompassData {
  current: CompassMarker | null;
  lastWeek: CompassMarker | null;
  lastMonth: CompassMarker | null;
  carry: number | null;       // IV - RV
  ivPercentile: number | null;
  rv: number | null;
  currentIV: number | null;
  loading: boolean;
}

function percentileRank(values: number[], target: number): number {
  const below = values.filter((v) => v < target).length;
  return (below / values.length) * 100;
}

export function useCompassData(
  asset: Asset,
  tenor: TenorLabel,
  range: TimeRange,
  currentIV: number | null
): CompassData {
  const [data, setData] = useState<CompassData>({
    current: null,
    lastWeek: null,
    lastMonth: null,
    carry: null,
    ivPercentile: null,
    rv: null,
    currentIV: null,
    loading: true,
  });

  const compute = useCallback(async () => {
    try {
      const tenorDays = TENOR_DAYS[tenor];
      if (!tenorDays || currentIV === null) return;

      const tenorHours = tenorDays * 24;
      const rangeHours = TIME_RANGE_HOURS[range];
      // Use the selected range for IV percentile (matches Vol Stats behavior)
      // Cap to what the backend has (max 720h = 30 days)
      const ivLookbackHours = Math.min(rangeHours, 720);

      // For tenors > 30D, use daily candles for spot percentile (Binance caps hourly at 1000 = ~41 days)
      const useDaily = tenorDays > 30;
      const symbol = getBinanceSymbol(asset);

      // Fetch spot candles (daily for long tenor percentile) and hourly candles (for RV) in parallel
      const [spotCandles, rvCandles, histRes] = await Promise.all([
        useDaily
          ? fetchBinanceCandles(symbol, "1d", Math.min(tenorDays + 60, 1000))
          : fetchBinanceCandlesPaginated(symbol, tenorHours + 48),
        useDaily
          ? fetchBinanceCandlesPaginated(symbol, tenorHours + 48) // hourly for RV
          : Promise.resolve([]), // reuse spotCandles
        fetch(`/api/history?tenor=${tenor}&hours=${ivLookbackHours}&currency=${asset}`),
      ]);
      const candles = spotCandles; // for spot percentile
      const rvData = useDaily ? rvCandles : spotCandles; // for RV computation

      if (candles.length === 0) {
        setData((prev) => ({ ...prev, loading: false }));
        return;
      }

      const historyPoints: { time: number; atm_iv: number | null }[] = histRes.ok
        ? await histRes.json()
        : [];

      // --- Spot percentile within tenor window ---
      const tenorPeriods = useDaily ? tenorDays : tenorHours;
      const tenorCandles = candles.slice(-Math.min(tenorPeriods, candles.length));
      const spotCloses = tenorCandles.map((c) => c.close);
      const currentSpot = spotCloses[spotCloses.length - 1];
      const spotPct = percentileRank(spotCloses, currentSpot);

      // --- IV percentile within range (matches Vol Stats: use last history value, not live) ---
      const ivValues = historyPoints
        .map((p) => p.atm_iv)
        .filter((v): v is number => v !== null);
      const historyIV = ivValues.length > 0 ? ivValues[ivValues.length - 1] : null;
      const ivPct =
        historyIV !== null && ivValues.length > 0
          ? percentileRank(ivValues, historyIV)
          : null;

      // --- Current RV (always hourly candles with sqrt(8760)) ---
      const rv = computeCurrentRV(rvData, tenorDays * 24, 8760);

      // --- Carry ---
      const carry = currentIV !== null && rv !== null ? currentIV - rv : null;

      // --- Current marker ---
      const current: CompassMarker | null =
        ivPct !== null ? { spotPct, ivPct } : null;

      // --- Last week marker (7 days ago) ---
      // Use full candle array (not tenor-sliced) so markers show even on short tenors
      let lastWeek: CompassMarker | null = null;
      const weekAgoMs = Date.now() - 7 * 24 * 3600 * 1000;
      const weekCandle = findClosestCandle(candles, weekAgoMs);
      if (weekCandle !== null && ivValues.length > 0) {
        const weekSpotPct = percentileRank(spotCloses, weekCandle);
        const weekAgoTime = Date.now() / 1000 - 7 * 24 * 3600;
        const weekIV = findClosestIV(historyPoints, weekAgoTime);
        if (weekIV !== null) {
          const weekIvPct = percentileRank(ivValues, weekIV);
          lastWeek = { spotPct: weekSpotPct, ivPct: weekIvPct };
        }
      }

      // --- Last month marker (30 days ago) ---
      let lastMonth: CompassMarker | null = null;
      const monthAgoMs = Date.now() - 30 * 24 * 3600 * 1000;
      const monthCandle = findClosestCandle(candles, monthAgoMs);
      if (monthCandle !== null && ivValues.length > 0) {
        const monthSpotPct = percentileRank(spotCloses, monthCandle);
        const monthAgoTime = Date.now() / 1000 - 30 * 24 * 3600;
        const monthIV = findClosestIV(historyPoints, monthAgoTime);
        if (monthIV !== null) {
          const monthIvPct = percentileRank(ivValues, monthIV);
          lastMonth = { spotPct: monthSpotPct, ivPct: monthIvPct };
        }
      }

      setData({
        current,
        lastWeek,
        lastMonth,
        carry: carry !== null ? Math.round(carry * 100) / 100 : null,
        ivPercentile: ivPct !== null ? Math.round(ivPct * 100) / 100 : null,
        rv: rv !== null ? Math.round(rv * 100) / 100 : null,
        currentIV,
        loading: false,
      });
    } catch {
      setData((prev) => ({ ...prev, loading: false }));
    }
  }, [asset, tenor, range, currentIV]);

  useEffect(() => {
    compute();
    const id = setInterval(compute, 300_000);
    return () => clearInterval(id);
  }, [compute]);

  return data;
}

function findClosestCandle(
  candles: { time: number; close: number }[],
  targetTimeMs: number,
  maxDistanceMs = 12 * 3600 * 1000
): number | null {
  let closest: number | null = null;
  let minDiff = Infinity;
  for (const c of candles) {
    const diff = Math.abs(c.time - targetTimeMs);
    if (diff < minDiff) {
      minDiff = diff;
      closest = c.close;
    }
  }
  return minDiff <= maxDistanceMs ? closest : null;
}

function findClosestIV(
  points: { time: number; atm_iv: number | null }[],
  targetTimeSec: number,
  maxDistanceSec = 12 * 3600 // reject matches more than 12 hours away
): number | null {
  let closest: number | null = null;
  let minDiff = Infinity;
  for (const p of points) {
    const diff = Math.abs(p.time - targetTimeSec);
    if (diff < minDiff && p.atm_iv !== null) {
      minDiff = diff;
      closest = p.atm_iv;
    }
  }
  return minDiff <= maxDistanceSec ? closest : null;
}
