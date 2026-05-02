"use client";

import { useState, useEffect } from "react";
import { Asset, TenorResponse, TimeRange, TIME_RANGE_HOURS } from "@/types";

export function useTenors(asset: Asset, changeRange: TimeRange = "24H") {
  const [data, setData] = useState<TenorResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let active = true;
    setIsLoading(true);

    async function fetchData() {
      try {
        const hours = TIME_RANGE_HOURS[changeRange];
        const res = await fetch(`/api/tenors?currency=${asset}&hours=${hours}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json: TenorResponse = await res.json();
        if (active) {
          setData(json);
          setError(json.errors?.length ? json.errors[0] : null);
          setIsLoading(false);
        }
      } catch (err) {
        if (active) {
          setError(err instanceof Error ? err.message : "Fetch failed");
          setIsLoading(false);
        }
      }
    }

    fetchData();
    const id = setInterval(fetchData, 60_000);

    return () => {
      active = false;
      clearInterval(id);
    };
  }, [asset, changeRange]);

  return { data, error, isLoading };
}
