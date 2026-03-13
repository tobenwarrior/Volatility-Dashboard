"use client";

import { useState, useCallback, useEffect, Fragment, type ChangeEvent } from "react";
import dynamic from "next/dynamic";
import { useAssetData } from "@/hooks/useAssetData";
import StatusBadge from "@/components/StatusBadge";
import PriceTicker from "@/components/PriceTicker";
import TenorTable from "@/components/TenorTable";
import TenorSelector from "@/components/TenorSelector";
import TimeRangeSelector from "@/components/TimeRangeSelector";
import LayoutMenu, { type Section } from "@/components/LayoutMenu";

const IvChart = dynamic(() => import("@/components/IvChart"), { ssr: false });
const TermStructureChart = dynamic(() => import("@/components/TermStructureChart"), {
  loading: () => <p className="py-10 text-center text-sm text-white/40">Loading...</p>,
});
const VolStats = dynamic(() => import("@/components/VolStats"), {
  loading: () => <p className="text-sm text-white/40">Loading...</p>,
});

const DEFAULT_SECTIONS: Section[] = [
  { id: "term-structure", label: "IV Term Structure", visible: true },
  { id: "iv-change", label: "ATM IV vs 24h Change", visible: true },
  { id: "historical", label: "Historical Charts", visible: true },
  { id: "vol-stats", label: "Vol Stats", visible: true },
];

const DEFERRED_SECTIONS = new Set(["iv-change", "historical", "vol-stats"]);

export default function Home() {
  const btc = useAssetData("BTC");
  const eth = useAssetData("ETH");
  const [sections, setSections] = useState(DEFAULT_SECTIONS);
  const [showRV, setShowRV] = useState<Record<string, boolean>>({ BTC: false, ETH: false });
  const [resetCounters, setResetCounters] = useState<Record<string, number>>({ BTC: 0, ETH: 0 });
  const [ready, setReady] = useState(false);
  useEffect(() => { setReady(true); }, []);
  const resetZoom = useCallback((asset: string) => {
    setResetCounters((prev) => ({ ...prev, [asset]: (prev[asset] ?? 0) + 1 }));
  }, []);

  const assets = [
    { asset: "BTC" as const, d: btc },
    { asset: "ETH" as const, d: eth },
  ];

  const renderSection = (id: string) => {
    switch (id) {
      case "term-structure":
        return assets.map(({ asset, d }) => (
          <div
            key={`tenor-${asset}`}
            className="rounded-xl border border-white/[0.08] bg-surface-raised p-5"
          >
            <h3 className="mb-4 text-sm font-medium uppercase tracking-wider text-deribit-gray">
              Implied Volatility Term Structure
            </h3>
            <TenorTable tenors={d.data?.tenors} />
          </div>
        ));

      case "iv-change":
        return assets.map(({ asset, d }) => (
          <div
            key={`chart-${asset}`}
            className="rounded-xl border border-white/[0.08] bg-surface-raised p-5"
          >
            <h3 className="mb-4 text-sm font-medium uppercase tracking-wider text-deribit-gray">
              ATM IV vs 24h IV Change
            </h3>
            <TermStructureChart tenors={d.data?.tenors} />
          </div>
        ));

      case "historical":
        return assets.map(({ asset, d }) => (
          <div
            key={`history-${asset}`}
            className="rounded-xl border border-white/[0.08] bg-surface-raised p-5"
          >
            <div className="mb-4 space-y-3">
              <div className="flex items-center">
                <h3 className="text-sm font-medium uppercase tracking-wider text-deribit-gray">
                  Historical Charts
                </h3>
                <button
                  onClick={() => resetZoom(asset)}
                  title="Reset zoom"
                  className="ml-auto flex items-center justify-center rounded-md bg-white/[0.06] px-2.5 py-1.5 text-deribit-gray transition-colors hover:bg-white/[0.1] hover:text-white"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="1 4 1 10 7 10" />
                    <path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10" />
                  </svg>
                </button>
              </div>
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
                <div className="h-4 w-px bg-white/[0.08]" />
                <label className="flex cursor-pointer items-center gap-1.5 text-xs">
                  <input
                    type="checkbox"
                    checked={showRV[asset] ?? false}
                    onChange={(e: ChangeEvent<HTMLInputElement>) =>
                      setShowRV((prev) => ({ ...prev, [asset]: e.target.checked }))
                    }
                    className="h-3 w-3 rounded border-white/20 bg-white/10 accent-amber-500"
                  />
                  <span className="font-medium text-amber-500">RV</span>
                </label>
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
                key={`${asset}-${d.selectedTenor}-${d.selectedRange}`}
                data={d.historyData}
                tenor={d.selectedTenor}
                tenorData={d.data?.tenors?.find(
                  (t) => t.label === d.selectedTenor
                )}
                resetCounter={resetCounters[asset] ?? 0}
                showRV={showRV[asset] ?? false}
              />
            )}
          </div>
        ));

      case "vol-stats":
        return assets.map(({ asset }) => (
          <div
            key={`stats-${asset}`}
            className="rounded-xl border border-white/[0.08] bg-surface-raised p-5"
          >
            <VolStats asset={asset} />
          </div>
        ));

      default:
        return null;
    }
  };

  return (
    <main className="mx-auto min-h-screen max-w-[1920px] px-4 py-4 lg:px-6 lg:py-5">
      <header className="mb-5 flex items-center gap-4">
        <LayoutMenu sections={sections} onChange={setSections} />
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
        {/* Price headers — always visible */}
        {assets.map(({ asset, d }) => (
          <div key={`header-${asset}`}>
            <PriceTicker
              price={d.price}
              prevPrice={d.prevPrice}
              stale={d.stale}
              asset={asset}
            />
          </div>
        ))}

        {/* Dynamic sections */}
        {sections
          .filter((s) => s.visible && (!DEFERRED_SECTIONS.has(s.id) || ready))
          .map((s) => (
            <Fragment key={s.id}>{renderSection(s.id)}</Fragment>
          ))}
      </div>
    </main>
  );
}
