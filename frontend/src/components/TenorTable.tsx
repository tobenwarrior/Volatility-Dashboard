import { TenorData } from "@/types";

interface TenorTableProps {
  tenors: TenorData[] | undefined;
}

function formatAge(hours: number | null): string {
  if (hours == null) return "";
  if (hours >= 23 && hours <= 25) return "";  // ~24h, no label needed
  if (hours < 1) return `${Math.round(hours * 60)}m`;
  if (hours >= 24) return `${Math.round(hours)}h`;
  return `${Math.round(hours)}h`;
}

function IvChange({ value, hours }: { value: number | null; hours: number | null }) {
  if (value == null) return <span className="text-white/40">&mdash;</span>;
  const color =
    value > 0
      ? "text-deribit-green"
      : value < 0
        ? "text-deribit-red"
        : "text-white/60";
  const sign = value > 0 ? "+" : "";
  const age = formatAge(hours);
  return (
    <span className={color}>
      {sign}{value.toFixed(2)}
      {age && <span className="ml-1 text-[10px] text-white/40">({age})</span>}
    </span>
  );
}

function SkewChange({ value, hours }: { value: number | null; hours: number | null }) {
  if (value == null) return <span className="text-white/40">&mdash;</span>;
  // Positive RR change = bullish shift (calls gaining), Negative = bearish shift
  const color =
    value > 0
      ? "text-deribit-green"
      : value < 0
        ? "text-deribit-red"
        : "text-white/60";
  const sign = value > 0 ? "+" : "";
  const age = formatAge(hours);
  return (
    <span className={color}>
      {sign}{value.toFixed(2)}
      {age && <span className="ml-1 text-[10px] text-white/40">({age})</span>}
    </span>
  );
}

function TenorRow({ tenor }: { tenor: TenorData }) {
  return (
    <tr className="border-b border-white/[0.06] hover:bg-white/[0.04] transition-colors">
      <td className="py-3 pr-4 text-sm font-semibold text-white">
        {tenor.label}
      </td>
      <td className="py-3 px-4 text-sm tabular-nums font-semibold text-deribit-blue">
        {tenor.atm_iv != null ? `${tenor.atm_iv.toFixed(2)}%` : "\u2014"}
      </td>
      <td className="py-3 px-4 text-sm tabular-nums">
        <IvChange value={tenor.dod_iv_change} hours={tenor.change_hours} />
      </td>
      <td className="py-3 px-4 text-sm tabular-nums text-white">
        {tenor.rr_25d != null
          ? `${tenor.rr_25d > 0 ? "+" : ""}${tenor.rr_25d.toFixed(2)}`
          : "\u2014"}
      </td>
      <td className="py-3 px-4 text-sm tabular-nums text-white/70">
        {tenor.rr_25d != null && tenor.atm_iv != null && tenor.atm_iv !== 0
          ? `${(tenor.rr_25d / tenor.atm_iv).toFixed(3)}`
          : "\u2014"}
      </td>
      <td className="py-3 pl-4 text-sm tabular-nums">
        <SkewChange value={tenor.dod_rr_change} hours={tenor.change_hours} />
      </td>
    </tr>
  );
}

export default function TenorTable({ tenors }: TenorTableProps) {
  if (!tenors || tenors.length === 0) {
    return <p className="text-sm text-white/40">Loading...</p>;
  }

  return (
    <div className="w-full">
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
                IV Chg
              </th>
              <th className="pb-3 px-4 text-xs font-medium uppercase tracking-wider text-deribit-gray">
                25&Delta; RR
              </th>
              <th className="pb-3 px-4 text-xs font-medium uppercase tracking-wider text-deribit-gray">
                Norm RR
              </th>
              <th className="pb-3 pl-4 text-xs font-medium uppercase tracking-wider text-deribit-gray">
                Skew Chg
              </th>
            </tr>
          </thead>
          <tbody>
            {tenors.map((t) => (
              <TenorRow key={t.label} tenor={t} />
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-4 flex items-center gap-3 text-[11px] text-white/40">
        <span>&Delta; = 25-delta</span>
        <span>&middot;</span>
        <span>RR = Call IV &minus; Put IV</span>
        <span>&middot;</span>
        <span>Norm = RR / ATM</span>
        <span>&middot;</span>
        <span className="text-deribit-green">+Skew</span>
        <span>= bullish shift</span>
        <span>&middot;</span>
        <span className="text-deribit-red">&minus;Skew</span>
        <span>= bearish shift</span>
      </div>
    </div>
  );
}
