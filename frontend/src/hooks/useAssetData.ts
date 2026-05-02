"use client";

import { useState } from "react";
import { useTenors } from "@/hooks/useTenors";
import { usePrice } from "@/hooks/usePrice";
import { useHistory } from "@/hooks/useHistory";
import { Asset, TenorLabel, TimeRange } from "@/types";

export function useAssetData(asset: Asset, topChangeRange: TimeRange = "24H") {
  const { data, error, isLoading } = useTenors(asset, topChangeRange);
  const { price, prevPrice, stale } = usePrice(asset);

  const [selectedTenor, setSelectedTenor] = useState<TenorLabel>("30D");
  const [selectedRange, setSelectedRange] = useState<TimeRange>("1H");

  const { data: historyData, isLoading: historyLoading } = useHistory(
    selectedTenor,
    selectedRange,
    asset
  );

  return {
    data,
    error,
    isLoading,
    price,
    prevPrice,
    stale,
    selectedTenor,
    setSelectedTenor,
    selectedRange,
    setSelectedRange,
    historyData,
    historyLoading,
  };
}
