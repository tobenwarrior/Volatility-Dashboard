"use client";

import { useState, useEffect, useCallback } from "react";
import { Asset, VolStatsEntry, TimeRange, TIME_RANGE_HOURS } from "@/types";

interface UseVolStatsResult {
  data: VolStatsEntry[];
  isLoading: boolean;
  error: string | null;
}

export function useVolStats(range: TimeRange, asset: Asset): UseVolStatsResult {
  const [data, setData] = useState<VolStatsEntry[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchStats = useCallback(async () => {
    const hours = TIME_RANGE_HOURS[range];
    try {
      const res = await fetch(`/api/vol-stats?hours=${hours}&currency=${asset}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json: VolStatsEntry[] = await res.json();
      setData(json);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Fetch failed");
    } finally {
      setIsLoading(false);
    }
  }, [range, asset]);

  useEffect(() => {
    setIsLoading(true);
    fetchStats();
    const id = setInterval(fetchStats, 10_000);
    return () => clearInterval(id);
  }, [fetchStats]);

  return { data, isLoading, error };
}
