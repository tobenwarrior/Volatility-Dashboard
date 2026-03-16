/** Shared RV computation utilities. */

import type { Candle } from "./binance";

export const PERIODS_PER_YEAR = 8760;

export const TENOR_DAYS: Record<string, number> = {
  "1W": 7,
  "2W": 14,
  "30D": 30,
  "60D": 60,
  "90D": 90,
  "180D": 180,
};

/**
 * Compute current (latest) RV from candles.
 * @param nReturns - number of return observations to use
 * @param periodsPerYear - annualization factor (8760 for hourly, 365 for daily)
 */
export function computeCurrentRV(
  candles: Candle[],
  nReturns: number,
  periodsPerYear: number = PERIODS_PER_YEAR
): number | null {
  if (candles.length < nReturns + 1) return null;

  const closes = candles.map((c) => c.close);
  const logReturns: number[] = [];
  for (let i = 1; i < closes.length; i++) {
    if (closes[i] > 0 && closes[i - 1] > 0) {
      logReturns.push(Math.log(closes[i] / closes[i - 1]));
    } else {
      logReturns.push(0);
    }
  }

  const window = logReturns.slice(-nReturns);
  if (window.length < nReturns) return null;

  const variance = window.reduce((a, r) => a + r * r, 0) / window.length;
  return Math.sqrt(variance) * Math.sqrt(periodsPerYear) * 100;
}
