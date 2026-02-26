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
import TenorSelector from "@/components/TenorSelector";
import TimeRangeSelector from "@/components/TimeRangeSelector";
import { TenorLabel, TimeRange } from "@/types";

const IvChart = dynamic(() => import("@/components/IvChart"), { ssr: false });

export default function Home() {
  const { data, error, isLoading } = useTenors();
  const { price, prevPrice, stale } = usePrice();

  const [selectedTenor, setSelectedTenor] = useState<TenorLabel>("30D");
  const [selectedRange, setSelectedRange] = useState<TimeRange>("1H");

  const { data: historyData, isLoading: historyLoading } = useHistory(
    selectedTenor,
    selectedRange
  );

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col items-center gap-10 px-6 py-16">
      <div className="flex w-full items-center justify-between">
        <h1 className="text-lg font-semibold tracking-tight text-white">
          BTC Volatility Estimator
        </h1>
        <StatusBadge isLoading={isLoading} error={error} />
      </div>

      <PriceTicker price={price} prevPrice={prevPrice} stale={stale} />

      <div className="w-full rounded-xl border border-white/[0.08] bg-surface-raised p-6">
        <h2 className="mb-5 text-sm font-medium uppercase tracking-wider text-deribit-gray">
          Implied Volatility Term Structure
        </h2>
        <TenorTable tenors={data?.tenors} />
      </div>

      <div className="w-full rounded-xl border border-white/[0.08] bg-surface-raised p-6">
        <div className="mb-5 space-y-3">
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
          <div className="flex h-[440px] items-center justify-center">
            <p className="text-sm text-white/40">Loading chart data...</p>
          </div>
        ) : historyData.length === 0 ? (
          <div className="flex h-[440px] items-center justify-center">
            <p className="text-sm text-white/40">
              No historical data yet. Charts will appear as data accumulates.
            </p>
          </div>
        ) : (
          <IvChart
            key={selectedTenor}
            data={historyData}
            tenor={selectedTenor}
            tenorData={data?.tenors?.find((t) => t.label === selectedTenor)}
          />
        )}
      </div>

      <div className="w-full rounded-xl border border-white/[0.08] bg-surface-raised p-6">
        <VolStats />
      </div>

      {data?.timestamp && (
        <p className="text-xs text-white/40">Last updated: {data.timestamp}</p>
      )}
    </main>
  );
}
