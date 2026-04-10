"use client";

import { useState, useEffect } from "react";
import dynamic from "next/dynamic";
import { useAssetData } from "@/hooks/useAssetData";
import { useCompassData } from "@/hooks/useCompassData";
import PriceTicker from "@/components/PriceTicker";
import TenorSelector from "@/components/TenorSelector";
import TimeRangeSelector from "@/components/TimeRangeSelector";
import StatusBadge from "@/components/StatusBadge";
import { TIME_RANGE_HOURS } from "@/types";

const VolCompass = dynamic(() => import("@/components/VolCompass"), { ssr: false });

export default function CompassPage() {
  const btc = useAssetData("BTC");
  const eth = useAssetData("ETH");
  const [showCompassHelp, setShowCompassHelp] = useState(false);
  const [ready, setReady] = useState(false);
  useEffect(() => { setReady(true); }, []);

  const btcIV = btc.data?.tenors?.find((t) => t.label === btc.selectedTenor)?.atm_iv ?? null;
  const ethIV = eth.data?.tenors?.find((t) => t.label === eth.selectedTenor)?.atm_iv ?? null;
  const btcCompass = useCompassData("BTC", btc.selectedTenor, TIME_RANGE_HOURS[btc.selectedRange], btcIV);
  const ethCompass = useCompassData("ETH", eth.selectedTenor, TIME_RANGE_HOURS[eth.selectedRange], ethIV);

  const assets = [
    { asset: "BTC" as const, d: btc, compass: btcCompass },
    { asset: "ETH" as const, d: eth, compass: ethCompass },
  ];

  return (
    <main className="mx-auto min-h-screen max-w-[1920px] px-4 py-4 lg:px-6 lg:py-5">
      <header className="mb-5 flex items-center gap-4">
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
        {/* Price headers */}
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

        {/* Vol Compass */}
        {ready && assets.map(({ asset, d, compass }) => (
          <div
            key={`compass-${asset}`}
            className="rounded-xl border border-white/[0.08] bg-surface-raised p-5"
          >
            <div className="mb-4 space-y-3">
              <h3 className="text-sm font-medium uppercase tracking-wider text-deribit-gray">
                Vol Compass
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
                <div className="h-4 w-px bg-white/[0.08]" />
                <button
                  onClick={() => setShowCompassHelp((p) => !p)}
                  className={`flex h-5 w-5 items-center justify-center rounded-full border text-[10px] font-bold transition-colors ${
                    showCompassHelp
                      ? "border-white/40 text-white/70"
                      : "border-white/20 text-white/40 hover:border-white/40 hover:text-white/70"
                  }`}
                  title="How to read this compass"
                >
                  ?
                </button>
              </div>
            </div>
            <VolCompass
              current={compass.current}
              lastWeek={compass.lastWeek}
              lastMonth={compass.lastMonth}
              carry={compass.carry}
              ivPercentile={compass.ivPercentile}
              currentIV={compass.currentIV}
              rv={compass.rv}
              loading={compass.loading}
              tenor={d.selectedTenor}
              showHelp={showCompassHelp}
              rangeLabel={d.selectedRange}
              ivHistoryDays={compass.ivHistoryDays}
            />
          </div>
        ))}
      </div>
    </main>
  );
}
