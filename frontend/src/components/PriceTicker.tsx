"use client";

import { useEffect, useState } from "react";

interface PriceTickerProps {
  price: number | null;
  prevPrice: number | null;
}

export default function PriceTicker({ price, prevPrice }: PriceTickerProps) {
  const [flash, setFlash] = useState<"green" | "red" | null>(null);

  useEffect(() => {
    if (price == null || prevPrice == null || price === prevPrice) return;
    setFlash(price > prevPrice ? "green" : "red");
    const timer = setTimeout(() => setFlash(null), 300);
    return () => clearTimeout(timer);
  }, [price, prevPrice]);

  const flashClass =
    flash === "green"
      ? "text-deribit-green"
      : flash === "red"
        ? "text-deribit-red"
        : "text-white";

  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs font-medium uppercase tracking-wider text-deribit-gray">
        BTC / USD
      </span>
      <span
        className={`text-3xl font-bold tabular-nums transition-colors duration-300 ${flashClass}`}
      >
        {price != null
          ? `$${price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
          : "\u2014"}
      </span>
    </div>
  );
}
