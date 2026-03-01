"use client";

import { useState } from "react";
import dynamic from "next/dynamic";
import { useTenors } from "@/hooks/useTenors";
import { usePrice } from "@/hooks/usePrice";
import { useHistory } from "@/hooks/useHistory";
import StatusBadge from "@/components/StatusBadge";
import PriceTicker from "@/components/PriceTicker";
import TenorTable from "@/components/TenorTable";
import VolStats from "@/components/VolStats";
import TermStructureChart from "@/components/TermStructureChart";
import TenorSelector from "@/components/TenorSelector";
import TimeRangeSelector from "@/components/TimeRangeSelector";
import AssetSelector from "@/components/AssetSelector";
import { Asset, TenorLabel, TimeRange } from "@/types";

const IvChart = dynamic(() => import("@/components/IvChart"), { ssr: false });

export default function Home() {
  const [asset, setAsset] = useState<Asset>("BTC");
  const { data, error, isLoading } = useTenors(asset);
  const { price, prevPrice, stale } = usePrice(asset);

  const [selectedTenor, setSelectedTenor] = useState<TenorLabel>("30D");
  const [selectedRange, setSelectedRange] = useState<TimeRange>("1H");

  const { data: historyData, isLoading: historyLoading } = useHistory(
    selectedTenor,
    selectedRange,
    asset
  );

  return (
    <main className="mx-auto min-h-screen max-w-7xl px-4 py-4 lg:px-6 lg:py-5">
      {/* Compact top bar */}
      <header className="mb-4 flex items-center gap-4 lg:mb-5">
        <h1 className="text-base font-semibold tracking-tight text-white">
          Volatility Estimator
        </h1>
        <AssetSelector selected={asset} onChange={setAsset} />
        <div className="h-4 w-px bg-white/[0.08]" />
        <PriceTicker price={price} prevPrice={prevPrice} stale={stale} asset={asset} />
        <div className="ml-auto flex items-center gap-3">
          {data?.timestamp && (
            <span className="hidden text-xs tabular-nums text-white/30 lg:inline">
              {new Date(data.timestamp).toLocaleTimeString([], {
                hour: "2-digit",
                minute: "2-digit",
                second: "2-digit",
              })}
            </span>
          )}
          <StatusBadge isLoading={isLoading} error={error} />
        </div>
      </header>

      {/* Dashboard grid */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 lg:gap-5">
        {/* IV Term Structure (top-left) */}
        <div className="rounded-xl border border-white/[0.08] bg-surface-raised p-5">
          <h2 className="mb-4 text-sm font-medium uppercase tracking-wider text-deribit-gray">
            Implied Volatility Term Structure
          </h2>
          <TenorTable tenors={data?.tenors} />
        </div>

        {/* ATM IV vs 24h IV Change (top-right) */}
        <div className="rounded-xl border border-white/[0.08] bg-surface-raised p-5">
          <h2 className="mb-4 text-sm font-medium uppercase tracking-wider text-deribit-gray">
            ATM IV vs 24h IV Change
          </h2>
          <TermStructureChart tenors={data?.tenors} />
        </div>

        {/* Historical Charts (bottom-left) */}
        <div className="rounded-xl border border-white/[0.08] bg-surface-raised p-5">
          <div className="mb-4 space-y-3">
            <h2 className="text-sm font-medium uppercase tracking-wider text-deribit-gray">
              Historical Charts
            </h2>
            <div className="flex flex-wrap items-center gap-3">
              <TenorSelector selected={selectedTenor} onChange={setSelectedTenor} />
              <div className="h-4 w-px bg-white/[0.08]" />
              <TimeRangeSelector selected={selectedRange} onChange={setSelectedRange} />
            </div>
          </div>

          {historyLoading && historyData.length === 0 ? (
            <div className="flex h-[360px] items-center justify-center">
              <p className="text-sm text-white/40">Loading chart data...</p>
            </div>
          ) : historyData.length === 0 ? (
            <div className="flex h-[360px] items-center justify-center">
              <p className="text-sm text-white/40">
                No historical data yet. Charts will appear as data accumulates.
              </p>
            </div>
          ) : (
            <IvChart
              key={`${asset}-${selectedTenor}`}
              data={historyData}
              tenor={selectedTenor}
              tenorData={data?.tenors?.find((t) => t.label === selectedTenor)}
            />
          )}
        </div>

        {/* Volatility Statistics (bottom-right) */}
        <div className="rounded-xl border border-white/[0.08] bg-surface-raised p-5">
          <VolStats asset={asset} />
        </div>
      </div>
    </main>
  );
}
