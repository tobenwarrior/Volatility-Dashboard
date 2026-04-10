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

// Tooltip on the 25Δ RR cell showing the raw 25Δ call/put IVs used to
// compute RR and Fly. Pure CSS (group-hover), no dependencies. Positioned
// ABOVE the cell to avoid clipping on the last row and to match the
// existing VolCompass tooltip pattern (bg-black/90 + backdrop-blur).
function RrCellWithTooltip({ tenor }: { tenor: TenorData }) {
  const hasBreakdown =
    tenor.call_25d_iv != null && tenor.put_25d_iv != null;

  return (
    <div className="group relative inline-block">
      <span className={hasBreakdown ? "cursor-help text-white" : "text-white"}>
        {formatSigned(tenor.rr_25d)}
      </span>
      {hasBreakdown && (
        <div
          role="tooltip"
          className="pointer-events-none absolute bottom-full left-1/2 z-30 mb-2 -translate-x-1/2 whitespace-nowrap rounded-lg border border-white/15 bg-black/90 px-3 py-2 text-left text-xs leading-relaxed opacity-0 shadow-xl backdrop-blur transition-opacity duration-150 group-hover:opacity-100"
        >
          <div className="mb-1.5 text-[10px] font-medium uppercase tracking-wider text-deribit-gray">
            25&Delta; IV Breakdown
          </div>
          <div className="flex justify-between gap-6 tabular-nums">
            <span className="text-white/60">Call IV</span>
            <span className="text-white">{tenor.call_25d_iv!.toFixed(2)}%</span>
          </div>
          <div className="flex justify-between gap-6 tabular-nums">
            <span className="text-white/60">Put IV</span>
            <span className="text-white">{tenor.put_25d_iv!.toFixed(2)}%</span>
          </div>
          <div className="my-1.5 border-t border-white/10" />
          <div className="flex justify-between gap-6 tabular-nums">
            <span className="text-white/60">RR</span>
            <span className="text-white">{formatSigned(tenor.rr_25d)}</span>
          </div>
          <div className="flex justify-between gap-6 tabular-nums">
            <span className="text-white/60">Fly</span>
            <span className="text-white">{formatSigned(tenor.bf_25d)}</span>
          </div>
          <div className="mt-1.5 text-[9px] text-white/40">
            RR = Call &minus; Put &nbsp;&middot;&nbsp; Fly = (C+P)/2 &minus; ATM
          </div>
        </div>
      )}
    </div>
  );
}

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
      <td className={NUM_CELL}>
        <RrCellWithTooltip tenor={tenor} />
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
      {/* overflow must stay visible so the RR tooltip can escape the cell.
          Safe because the table is w-full table-fixed with 7 fractional
          cols — it cannot horizontally overflow on any reasonable screen. */}
      <div>
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
