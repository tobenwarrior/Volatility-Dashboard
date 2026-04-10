import { TenorData } from "@/types";

interface TenorTableProps {
  tenors: TenorData[] | undefined;
}

function formatAge(hours: number | null): string {
  if (hours == null) return "";
  if (hours >= 23 && hours <= 25) return "";  // ~24h, no label needed
  if (hours < 1) return `${Math.round(hours * 60)}m`;
  return `${Math.round(hours)}h`;
}

function formatSigned(value: number | null, digits = 2): string {
  if (value == null) return "\u2014";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(digits)}`;
}

function ChangeCell({ value, hours }: { value: number | null; hours: number | null }) {
  if (value == null) return <span className="text-white/40">&mdash;</span>;
  const color =
    value > 0
      ? "text-deribit-green"
      : value < 0
        ? "text-deribit-red"
        : "text-white/60";
  const age = formatAge(hours);
  return (
    <span className={color}>
      {formatSigned(value)}
      {age && <span className="ml-1 text-[10px] text-white/40">({age})</span>}
    </span>
  );
}

// Shared class strings so header + data cells stay visually aligned.
const NUM_HEADER = "pb-3 text-center text-xs font-medium uppercase tracking-wider text-deribit-gray";
const NUM_CELL = "py-3 text-center text-sm tabular-nums";

function TenorRow({ tenor }: { tenor: TenorData }) {
  const normRr =
    tenor.rr_25d != null && tenor.atm_iv != null && tenor.atm_iv !== 0
      ? tenor.rr_25d / tenor.atm_iv
      : null;

  return (
    <tr className="border-b border-white/[0.06] hover:bg-white/[0.04] transition-colors">
      <td className="py-3 pl-1 text-left text-sm font-semibold text-white">
        {tenor.label}
      </td>
      <td className={`${NUM_CELL} font-semibold text-deribit-blue`}>
        {tenor.atm_iv != null ? `${tenor.atm_iv.toFixed(2)}%` : "\u2014"}
      </td>
      <td className={NUM_CELL}>
        <ChangeCell value={tenor.dod_iv_change} hours={tenor.change_hours} />
      </td>
      <td className={`${NUM_CELL} text-white`}>
        {formatSigned(tenor.rr_25d)}
      </td>
      <td className={NUM_CELL}>
        <ChangeCell value={tenor.dod_rr_change} hours={tenor.change_hours} />
      </td>
      <td className={`${NUM_CELL} text-white`}>
        {formatSigned(tenor.bf_25d)}
      </td>
      <td className={`${NUM_CELL} text-white/70`}>
        {formatSigned(normRr, 3)}
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
        <table className="w-full table-fixed">
          {/* Narrower Tenor col gives the numerical columns more breathing room */}
          <colgroup>
            <col className="w-[9%]" />
            <col className="w-[14%]" />
            <col className="w-[14%]" />
            <col className="w-[14%]" />
            <col className="w-[16%]" />
            <col className="w-[14%]" />
            <col className="w-[19%]" />
          </colgroup>
          <thead>
            <tr className="border-b border-white/[0.08]">
              <th className="pb-3 pl-1 text-left text-xs font-medium uppercase tracking-wider text-deribit-gray">
                Tenor
              </th>
              <th className={NUM_HEADER}>ATM IV</th>
              <th className={NUM_HEADER}>IV Chg</th>
              <th className={NUM_HEADER}>25&Delta; RR</th>
              <th className={NUM_HEADER}>Skew Chg</th>
              <th className={NUM_HEADER}>Fly</th>
              <th className={NUM_HEADER}>Norm RR</th>
            </tr>
          </thead>
          <tbody>
            {tenors.map((t) => (
              <TenorRow key={t.label} tenor={t} />
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-white/40">
        <span>&Delta; = 25-delta</span>
        <span>&middot;</span>
        <span>RR = Call IV &minus; Put IV</span>
        <span>&middot;</span>
        <span>Fly = (Call + Put)/2 &minus; ATM</span>
        <span>&middot;</span>
        <span>Norm RR = RR / ATM</span>
        <span>&middot;</span>
        <span className="whitespace-nowrap">
          <span className="text-deribit-green">+Skew Chg</span> = bullish shift
        </span>
        <span>&middot;</span>
        <span className="whitespace-nowrap">
          <span className="text-deribit-red">&minus;Skew Chg</span> = bearish shift
        </span>
      </div>
    </div>
  );
}
