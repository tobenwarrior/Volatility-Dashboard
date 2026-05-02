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
  const endTime = Math.floor(Date.now() / 3_600_000) * 3_600_000 - 1;
  const res = await fetch(
    `https://api.binance.com/api/v3/klines?symbol=${symbol}&interval=${interval}&limit=${limit}&endTime=${endTime}`
  );
  if (!res.ok) return [];
  const raw: unknown[][] = await res.json();
  return raw
    .filter((c) => {
      const closeTime = typeof c[6] === "number" ? c[6] : (c[0] as number) + 3_600_000 - 1;
      return closeTime <= Date.now();
    })
    .map((c) => ({
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
  let endTime = Math.floor(Date.now() / 3_600_000) * 3_600_000 - 1;

  while (allCandles.length < totalNeeded) {
    const remaining = totalNeeded - allCandles.length;
    const limit = Math.min(remaining, 1000);
    const res = await fetch(
      `https://api.binance.com/api/v3/klines?symbol=${symbol}&interval=${interval}&limit=${limit}&endTime=${endTime}`
    );
    if (!res.ok) break;
    const raw: unknown[][] = await res.json();
    if (raw.length === 0) break;

    const batch = raw
      .filter((c) => {
        const closeTime = typeof c[6] === "number" ? c[6] : (c[0] as number) + 3_600_000 - 1;
        return closeTime <= Date.now();
      })
      .map((c) => ({
        time: c[0] as number,
        close: parseFloat(c[4] as string),
      }));

    if (batch.length === 0) break;

    allCandles.unshift(...batch);
    // Move endTime to just before the oldest completed candle in this batch
    endTime = batch[0].time - 1;
  }

  return allCandles;
}
