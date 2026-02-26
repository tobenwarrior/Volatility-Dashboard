"use client";

import { useState, useEffect, useRef } from "react";

export function usePrice() {
  const [price, setPrice] = useState<number | null>(null);
  const [prevPrice, setPrevPrice] = useState<number | null>(null);
  const prevRef = useRef<number | null>(null);

  useEffect(() => {
    let active = true;

    async function fetchPrice() {
      try {
        const res = await fetch("/api/price");
        if (!res.ok) return;
        const json = await res.json();
        if (active && json.price != null) {
          setPrevPrice(prevRef.current);
          prevRef.current = json.price;
          setPrice(json.price);
        }
      } catch {
        // silent — price will show stale
      }
    }

    fetchPrice();
    const id = setInterval(fetchPrice, 1000);

    return () => {
      active = false;
      clearInterval(id);
    };
  }, []);

  return { price, prevPrice };
}
