"use client";

import { useState, useEffect, useRef } from "react";

export function usePrice() {
  const [price, setPrice] = useState<number | null>(null);
  const [prevPrice, setPrevPrice] = useState<number | null>(null);
  const [stale, setStale] = useState(false);
  const prevRef = useRef<number | null>(null);
  const failCount = useRef(0);

  useEffect(() => {
    let active = true;

    async function fetchPrice() {
      try {
        const res = await fetch("/api/price");
        if (!res.ok) {
          failCount.current++;
          if (failCount.current >= 5) setStale(true);
          return;
        }
        const json = await res.json();
        if (active && json.price != null) {
          failCount.current = 0;
          setStale(false);
          setPrevPrice(prevRef.current);
          prevRef.current = json.price;
          setPrice(json.price);
        }
      } catch {
        failCount.current++;
        if (failCount.current >= 5 && active) setStale(true);
      }
    }

    fetchPrice();
    const id = setInterval(fetchPrice, 1000);

    return () => {
      active = false;
      clearInterval(id);
    };
  }, []);

  return { price, prevPrice, stale };
}
