"use client";

import { useState, useEffect, useCallback } from "react";
import { Asset, TenorLabel } from "@/types";

export interface RVPoint {
  time: number;
  rv: number;
}

export function useRVSeries(tenor: TenorLabel, asset: Asset, enabled: boolean) {
  const [data, setData] = useState<RVPoint[]>([]);

  const fetchRV = useCallback(async () => {
    if (!enabled) return;
    try {
      const res = await fetch(`/api/rv-series?tenor=${tenor}&currency=${asset}`);
      if (!res.ok) return;
      const json: RVPoint[] = await res.json();
      setData(json);
    } catch {
      // silently ignore — RV is optional overlay
    }
  }, [tenor, asset, enabled]);

  useEffect(() => {
    if (!enabled) {
      setData([]);
      return;
    }
    fetchRV();
    const id = setInterval(fetchRV, 300_000); // refresh every 5 min (matches cache TTL)
    return () => clearInterval(id);
  }, [fetchRV, enabled]);

  return data;
}
