export interface TenorData {
  label: string;
  target_days: number;
  atm_iv: number | null;
  rr_25d: number | null;
  dod_iv_change: number | null;
  dod_rr_change: number | null;
  change_hours: number | null;
  method: string | null;
  error: string | null;
}

export interface VolStatsEntry {
  label: string;
  current_iv: number | null;
  iv_high: number | null;
  iv_low: number | null;
  iv_percentile: number | null;
  iv_zscore: number | null;
  samples: number;
  lookback_hours: number | null;
}

export interface TenorResponse {
  timestamp: string;
  spot_price: number;
  tenors: TenorData[];
  errors: string[];
}

export interface PriceData {
  price: number | null;
}

export interface HistoryPoint {
  time: number;
  atm_iv: number | null;
  rr_25d: number | null;
}

export type Asset = "BTC" | "ETH";
export type TenorLabel = "1W" | "2W" | "30D" | "60D" | "90D" | "180D";
export type TimeRange = "1H" | "4H" | "24H" | "7D";

export const TIME_RANGE_HOURS: Record<TimeRange, number> = {
  "1H": 1,
  "4H": 4,
  "24H": 24,
  "7D": 168,
};