/** Shared Binance spot candle fetcher (client-side, no CORS issues). */

export interface Candle {
  time: number;   // open time in ms
  close: number;
}

const BINANCE_SYMBOLS: Record<string, string> = {
  BTC: "BTCUSDT",
  ETH: "ETHUSDT",
};

export function getBinanceSymbol(asset: string): string {
  return BINANCE_SYMBOLS[asset] ?? `${asset}USDT`;
}

export async function fetchBinanceCandles(
  symbol: string,
  interval = "1h",
  limit = 1000
): Promise<Candle[]> {
  const res = await fetch(
    `https://api.binance.com/api/v3/klines?symbol=${symbol}&interval=${interval}&limit=${limit}`
  );
  if (!res.ok) return [];
  const raw: unknown[][] = await res.json();
  return raw.map((c) => ({
    time: c[0] as number,
    close: parseFloat(c[4] as string),
  }));
}

/**
 * Fetch more than 1000 hourly candles by paginating backwards.
 * Each request fetches up to 1000 candles using endTime to paginate.
 */
export async function fetchBinanceCandlesPaginated(
  symbol: string,
  totalNeeded: number,
  interval = "1h"
): Promise<Candle[]> {
  // If under 1000, just do a single fetch
  if (totalNeeded <= 1000) {
    return fetchBinanceCandles(symbol, interval, totalNeeded);
  }

  const allCandles: Candle[] = [];
  let endTime = Date.now();

  while (allCandles.length < totalNeeded) {
    const remaining = totalNeeded - allCandles.length;
    const limit = Math.min(remaining, 1000);
    const res = await fetch(
      `https://api.binance.com/api/v3/klines?symbol=${symbol}&interval=${interval}&limit=${limit}&endTime=${endTime}`
    );
    if (!res.ok) break;
    const raw: unknown[][] = await res.json();
    if (raw.length === 0) break;

    const batch = raw.map((c) => ({
      time: c[0] as number,
      close: parseFloat(c[4] as string),
    }));

    allCandles.unshift(...batch);
    // Move endTime to just before the oldest candle in this batch
    endTime = batch[0].time - 1;
  }

  return allCandles;
}
