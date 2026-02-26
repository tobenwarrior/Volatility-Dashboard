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

export interface TenorResponse {
  timestamp: string;
  spot_price: number;
  tenors: TenorData[];
  errors: string[];
}

export interface PriceData {
  price: number | null;
}
