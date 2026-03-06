"use client";

import { useState, useEffect, useCallback } from "react";
import { Asset, HistoryPoint, TenorLabel, TimeRange, TIME_RANGE_HOURS } from "@/types";

interface UseHistoryResult {
  data: HistoryPoint[];
  isLoading: boolean;
  error: string | null;
}

export function useHistory(tenor: TenorLabel, range: TimeRange, asset: Asset): UseHistoryResult {
  const [data, setData] = useState<HistoryPoint[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchHistory = useCallback(async () => {
    const hours = TIME_RANGE_HOURS[range];
    try {
      const res = await fetch(`/api/history?tenor=${tenor}&hours=${hours}&currency=${asset}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json: HistoryPoint[] = await res.json();
      setData(json);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Fetch failed");
    } finally {
      setIsLoading(false);
    }
  }, [tenor, range, asset]);

  useEffect(() => {
    setIsLoading(true);
    fetchHistory();
    const id = setInterval(fetchHistory, 60_000);
    return () => clearInterval(id);
  }, [fetchHistory]);

  return { data, isLoading, error };
}
