"use client";

import { useState } from "react";
import { VolStatsEntry, TimeRange } from "@/types";
import { useVolStats } from "@/hooks/useVolStats";
import TimeRangeSelector from "@/components/TimeRangeSelector";

function PercentileCell({ value }: { value: number | null }) {
  if (value == null) return <span className="text-white/40">&mdash;</span>;
  // Red = IV rich (expensive, sell signal), Green = IV cheap (opportunity, buy signal)
  const color =
    value >= 70
      ? "text-deribit-red"
      : value <= 30
        ? "text-deribit-green"
        : "text-white/80";
  return <span className={color}>{Math.round(value)}th</span>;
}

function ZScoreCell({ value }: { value: number | null }) {
  if (value == null) return <span className="text-white/40">&mdash;</span>;
  // Red = IV elevated (rich), Green = IV depressed (cheap)
  const color =
    value > 1
      ? "text-deribit-red"
      : value < -1
        ? "text-deribit-green"
        : "text-white/80";
  const sign = value > 0 ? "+" : "";
  return <span className={color}>{sign}{value.toFixed(2)}</span>;
}

function PercentileBar({ value }: { value: number | null }) {
  if (value == null) return null;
  const fill =
    value >= 70
      ? "bg-deribit-red/60"
      : value <= 30
        ? "bg-deribit-green/60"
        : "bg-deribit-blue/40";
  return (
    <div className="mt-1 h-1 w-full rounded-full bg-white/[0.06]">
      <div
        className={`h-full rounded-full ${fill}`}
        style={{ width: `${Math.min(100, Math.max(0, value))}%` }}
      />
    </div>
  );
}

function StatsRow({ entry }: { entry: VolStatsEntry }) {
  return (
    <tr className="border-b border-white/[0.06] hover:bg-white/[0.04] transition-colors">
      <td className="py-3 pr-4 text-sm font-semibold text-white">
        {entry.label}
      </td>
      <td className="py-3 px-4 text-sm tabular-nums font-semibold text-deribit-blue">
        {entry.current_iv != null ? `${entry.current_iv.toFixed(2)}%` : "\u2014"}
      </td>
      <td className="py-3 px-4 text-sm tabular-nums">
        <PercentileCell value={entry.iv_percentile} />
        <PercentileBar value={entry.iv_percentile} />
      </td>
      <td className="py-3 px-4 text-sm tabular-nums text-white/80">
        {entry.iv_high != null ? `${entry.iv_high.toFixed(2)}%` : "\u2014"}
      </td>
      <td className="py-3 px-4 text-sm tabular-nums text-white/80">
        {entry.iv_low != null ? `${entry.iv_low.toFixed(2)}%` : "\u2014"}
      </td>
      <td className="py-3 pl-4 text-sm tabular-nums">
        <ZScoreCell value={entry.iv_zscore} />
      </td>
    </tr>
  );
}

export default function VolStats() {
  const [range, setRange] = useState<TimeRange>("7D");
  const { data, isLoading } = useVolStats(range);

  const hasStats = data.length > 0 && data.some((e) => e.iv_percentile != null);

  // Derive lookback info from first entry with data
  const withData = data.find((e) => e.lookback_hours != null);
  const lookbackDays = withData?.lookback_hours
    ? Math.round(withData.lookback_hours / 24 * 10) / 10
    : null;
  const samples = withData?.samples ?? null;

  return (
    <div className="w-full">
      <div className="mb-5 space-y-3">
        <h2 className="text-sm font-medium uppercase tracking-wider text-deribit-gray">
          Volatility Statistics
        </h2>
        <TimeRangeSelector selected={range} onChange={setRange} />
      </div>

      {isLoading && data.length === 0 ? (
        <p className="text-sm text-white/40">Loading...</p>
      ) : !hasStats ? (
        <p className="text-sm text-white/40">
          No data in this time window yet. Stats will appear as data accumulates.
        </p>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-white/[0.08]">
                  <th className="pb-3 pr-4 text-xs font-medium uppercase tracking-wider text-deribit-gray">
                    Tenor
                  </th>
                  <th className="pb-3 px-4 text-xs font-medium uppercase tracking-wider text-deribit-gray">
                    ATM IV
                  </th>
                  <th className="pb-3 px-4 text-xs font-medium uppercase tracking-wider text-deribit-gray">
                    IV Pctl
                  </th>
                  <th className="pb-3 px-4 text-xs font-medium uppercase tracking-wider text-deribit-gray">
                    High
                  </th>
                  <th className="pb-3 px-4 text-xs font-medium uppercase tracking-wider text-deribit-gray">
                    Low
                  </th>
                  <th className="pb-3 pl-4 text-xs font-medium uppercase tracking-wider text-deribit-gray">
                    Z-Score
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.map((e) => (
                  <StatsRow key={e.label} entry={e} />
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-4 flex items-center gap-3 text-[11px] text-white/40">
            {lookbackDays != null && (
              <span>Lookback: {lookbackDays}d</span>
            )}
            {samples != null && (
              <>
                <span>&middot;</span>
                <span>{samples.toLocaleString()} samples</span>
              </>
            )}
            <span>&middot;</span>
            <span className="text-deribit-red">&ge;70th</span>
            <span>= IV rich (expensive)</span>
            <span>&middot;</span>
            <span className="text-deribit-green">&le;30th</span>
            <span>= IV cheap (opportunity)</span>
          </div>
        </>
      )}
    </div>
  );
}
