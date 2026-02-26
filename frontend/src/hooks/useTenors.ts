"use client";

import { useState, useEffect } from "react";
import { TenorResponse } from "@/types";

export function useTenors() {
  const [data, setData] = useState<TenorResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let active = true;

    async function fetchData() {
      try {
        const res = await fetch("/api/tenors");
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
    const id = setInterval(fetchData, 5000);

    return () => {
      active = false;
      clearInterval(id);
    };
  }, []);

  return { data, error, isLoading };
}
