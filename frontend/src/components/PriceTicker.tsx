"use client";

import { useEffect, useState } from "react";

interface PriceTickerProps {
  price: number | null;
  prevPrice: number | null;
  stale?: boolean;
  asset?: string;
}

export default function PriceTicker({ price, prevPrice, stale, asset = "BTC" }: PriceTickerProps) {
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
    <div className="flex items-center gap-2">
      <span className="text-xs font-medium uppercase tracking-wider text-deribit-gray">
        {asset} / USD
      </span>
      <span
        className={`text-base font-bold tabular-nums transition-colors duration-300 ${flashClass}`}
      >
        {price != null
          ? `$${price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
          : "\u2014"}
      </span>
      {stale && (
        <span className="rounded bg-deribit-red/20 px-1.5 py-0.5 text-[10px] font-medium text-deribit-red">
          STALE
        </span>
      )}
    </div>
  );
}
