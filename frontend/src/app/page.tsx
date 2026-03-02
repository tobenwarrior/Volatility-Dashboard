"use client";

import dynamic from "next/dynamic";
import { useAssetData } from "@/hooks/useAssetData";
import StatusBadge from "@/components/StatusBadge";
import PriceTicker from "@/components/PriceTicker";
import TenorTable from "@/components/TenorTable";
import VolStats from "@/components/VolStats";
import TermStructureChart from "@/components/TermStructureChart";
import TenorSelector from "@/components/TenorSelector";
import TimeRangeSelector from "@/components/TimeRangeSelector";

const IvChart = dynamic(() => import("@/components/IvChart"), { ssr: false });

export default function Home() {
  const btc = useAssetData("BTC");
  const eth = useAssetData("ETH");

  return (
    <main className="mx-auto min-h-screen max-w-[1920px] px-4 py-4 lg:px-6 lg:py-5">
      <header className="mb-5 flex items-center gap-4">
        <h1 className="text-base font-semibold tracking-tight text-white">
          Volatility Dashboard
        </h1>
        <div className="ml-auto flex items-center gap-2">
          {btc.data?.timestamp && (
            <span className="hidden text-xs text-white/30 lg:inline">
              Last updated{" "}
              <span className="tabular-nums">
                {new Date(btc.data.timestamp).toLocaleTimeString([], {
                  hour: "2-digit",
                  minute: "2-digit",
                  second: "2-digit",
                })}
              </span>
            </span>
          )}
          <StatusBadge isLoading={btc.isLoading} error={btc.error || eth.error} />
        </div>
      </header>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2 xl:gap-5">
        {/* Row 1: Column headers */}
        {[
          { asset: "BTC" as const, d: btc },
          { asset: "ETH" as const, d: eth },
        ].map(({ asset, d }) => (
          <div key={`header-${asset}`}>
            <PriceTicker
              price={d.price}
              prevPrice={d.prevPrice}
              stale={d.stale}
              asset={asset}
            />
          </div>
        ))}

        {/* Row 2: IV Term Structure */}
        {[
          { asset: "BTC" as const, d: btc },
          { asset: "ETH" as const, d: eth },
        ].map(({ asset, d }) => (
          <div
            key={`tenor-${asset}`}
            className="rounded-xl border border-white/[0.08] bg-surface-raised p-5"
          >
            <h3 className="mb-4 text-sm font-medium uppercase tracking-wider text-deribit-gray">
              Implied Volatility Term Structure
            </h3>
            <TenorTable tenors={d.data?.tenors} />
          </div>
        ))}

        {/* Row 3: ATM IV vs 24h IV Change */}
        {[
          { asset: "BTC" as const, d: btc },
          { asset: "ETH" as const, d: eth },
        ].map(({ asset, d }) => (
          <div
            key={`chart-${asset}`}
            className="rounded-xl border border-white/[0.08] bg-surface-raised p-5"
          >
            <h3 className="mb-4 text-sm font-medium uppercase tracking-wider text-deribit-gray">
              ATM IV vs 24h IV Change
            </h3>
            <TermStructureChart tenors={d.data?.tenors} />
          </div>
        ))}

        {/* Row 4: Historical Charts */}
        {[
          { asset: "BTC" as const, d: btc },
          { asset: "ETH" as const, d: eth },
        ].map(({ asset, d }) => (
          <div
            key={`history-${asset}`}
            className="rounded-xl border border-white/[0.08] bg-surface-raised p-5"
          >
            <div className="mb-4 space-y-3">
              <h3 className="text-sm font-medium uppercase tracking-wider text-deribit-gray">
                Historical Charts
              </h3>
              <div className="flex flex-wrap items-center gap-3">
                <TenorSelector
                  selected={d.selectedTenor}
                  onChange={d.setSelectedTenor}
                />
                <div className="h-4 w-px bg-white/[0.08]" />
                <TimeRangeSelector
                  selected={d.selectedRange}
                  onChange={d.setSelectedRange}
                />
              </div>
            </div>

            {d.historyLoading && d.historyData.length === 0 ? (
              <div className="flex h-[360px] items-center justify-center">
                <p className="text-sm text-white/40">Loading chart data...</p>
              </div>
            ) : d.historyData.length === 0 ? (
              <div className="flex h-[360px] items-center justify-center">
                <p className="text-sm text-white/40">
                  No historical data yet. Charts will appear as data
                  accumulates.
                </p>
              </div>
            ) : (
              <IvChart
                key={`${asset}-${d.selectedTenor}`}
                data={d.historyData}
                tenor={d.selectedTenor}
                tenorData={d.data?.tenors?.find(
                  (t) => t.label === d.selectedTenor
                )}
              />
            )}
          </div>
        ))}

        {/* Row 5: Volatility Statistics */}
        {[
          { asset: "BTC" as const },
          { asset: "ETH" as const },
        ].map(({ asset }) => (
          <div
            key={`stats-${asset}`}
            className="rounded-xl border border-white/[0.08] bg-surface-raised p-5"
          >
            <VolStats asset={asset} />
          </div>
        ))}
      </div>
    </main>
  );
}
