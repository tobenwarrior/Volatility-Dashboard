"use client";

import { type CompassMarker } from "@/hooks/useCompassData";

interface VolCompassProps {
  current: CompassMarker | null;
  lastWeek: CompassMarker | null;
  lastMonth: CompassMarker | null;
  carry: number | null;
  ivPercentile: number | null;
  currentIV: number | null;
  rv: number | null;
  loading: boolean;
  tenor: string;
  showHelp: boolean;
}

function getStrategy(m: CompassMarker): string {
  // High spotPct = RIGHT = bearish (price is high, might reverse)
  // Low spotPct = LEFT = bullish (price is low, might bounce)
  const bearish = m.spotPct > 50;
  const highIV = m.ivPct > 50;

  // Strong directional (outer ring)
  if (m.ivPct > 75) {
    if (m.spotPct < 35) return "SELL PUT";       // left + high IV
    if (m.spotPct > 65) return "SELL CALL";      // right + high IV
    return "SELL STRADDLE/STRANGLE";
  }
  if (m.ivPct < 25) {
    if (m.spotPct < 35) return "BUY CALL";       // left + low IV
    if (m.spotPct > 65) return "BUY PUT";        // right + low IV
    return "BUY STRADDLE/STRANGLE";
  }
  // Mid zone (spreads or risk reversals)
  if (m.spotPct < 35) return highIV ? "SELL PUT SPREAD" : "BUY CALL SPREAD";
  if (m.spotPct > 65) return highIV ? "SELL CALL SPREAD" : "BUY PUT SPREAD";
  if (!bearish && highIV) return "SELL PUT SPREAD";
  if (!bearish && !highIV) return "BUY CALL SPREAD";
  if (bearish && highIV) return "SELL CALL SPREAD";
  return "BUY PUT SPREAD";
}

const CX = 200;
const CY = 200;
const R_OUTER = 170;
const R_MID = 120;
const R_INNER = 70;

/** Map percentile (0–100) to compass position.
 *  Spot: high percentile → RIGHT (bearish — price near highs), low → LEFT (bullish — price near lows)
 *  IV:   high percentile → TOP (sell vol), low → BOTTOM (buy vol)
 */
function markerPos(m: CompassMarker): { x: number; y: number } {
  // Normalize to [-1, 1]
  const nx = (m.spotPct - 50) / 50;  // high spot pct = right (bearish — price is high)
  const ny = -(m.ivPct - 50) / 50;  // high IV pct = top (sell vol — SVG y is down)

  // Clamp to circle
  const dist = Math.sqrt(nx * nx + ny * ny);
  const scale = dist > 1 ? 1 / dist : 1;

  return {
    x: CX + nx * scale * (R_OUTER - 10),
    y: CY + ny * scale * (R_OUTER - 10),
  };
}

function CrossMark({
  x,
  y,
  size,
  color,
  glow,
  filterId,
}: {
  x: number;
  y: number;
  size: number;
  color: string;
  glow?: boolean;
  filterId?: string;
}) {
  const half = size / 2;
  const sw = size > 10 ? 3 : 2;
  return (
    <g filter={glow && filterId ? `url(#${filterId})` : undefined}>
      <line
        x1={x - half} y1={y - half} x2={x + half} y2={y + half}
        stroke={color} strokeWidth={sw} strokeLinecap="round"
      />
      <line
        x1={x + half} y1={y - half} x2={x - half} y2={y + half}
        stroke={color} strokeWidth={sw} strokeLinecap="round"
      />
    </g>
  );
}

export default function VolCompass({
  current,
  lastWeek,
  lastMonth,
  carry,
  ivPercentile,
  currentIV,
  rv,
  loading,
  tenor,
  showHelp,
}: VolCompassProps) {
  const strategy = current ? getStrategy(current) : null;
  const ringStyle = {
    fill: "none",
    strokeWidth: 1,
  };

  return (
    <div className="flex flex-col items-center gap-3">
      {showHelp && (
        <div className="w-full rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2.5 text-[10px] leading-relaxed text-white/50">
          <p className="mb-1.5 font-semibold text-white/70">How to read the Vol Compass</p>
          <p className="mb-1">
            The compass suggests an options strategy based on where <span className="text-blue-400">IV</span> and <span className="text-purple-400">spot price</span> sit relative to their {tenor} historical range.
          </p>
          <p className="mb-1">
            <span className="text-white/60">Y-axis (vertical):</span> {tenor} ATM IV percentile. Top = IV is high (expensive options — sell vol). Bottom = IV is low (cheap options — buy vol).
          </p>
          <p className="mb-1">
            <span className="text-white/60">X-axis (horizontal):</span> Spot price percentile in {tenor} range. Right = spot near highs (extended — bearish lean). Left = spot near lows (oversold — bullish lean).
          </p>
          <p className="mb-1">
            <span className="text-white/60">Carry</span> = IV &minus; RV. Positive = options are rich (favor selling). Negative = options are cheap (favor buying).
          </p>
          <p className="text-white/40">
            Crosses show how the regime shifted: <span className="text-[#22c55e]">green</span> = now, gray = last week/month.
          </p>
        </div>
      )}
      <svg viewBox="0 0 400 400" className="w-full max-w-[360px]">
        <defs>
          <filter id="glow-green" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="4" result="blur" />
            <feFlood floodColor="#22c55e" floodOpacity="0.6" result="color" />
            <feComposite in="color" in2="blur" operator="in" result="glow" />
            <feMerge>
              <feMergeNode in="glow" />
              <feMergeNode in="glow" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          <filter id="glow-week" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="2.5" result="blur" />
            <feFlood floodColor="#ffffff" floodOpacity="0.3" result="color" />
            <feComposite in="color" in2="blur" operator="in" result="glow" />
            <feMerge>
              <feMergeNode in="glow" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          <filter id="glow-month" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="1.5" result="blur" />
            <feFlood floodColor="#ffffff" floodOpacity="0.15" result="color" />
            <feComposite in="color" in2="blur" operator="in" result="glow" />
            <feMerge>
              <feMergeNode in="glow" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* Background rings */}
        <circle cx={CX} cy={CY} r={R_OUTER} stroke="rgba(255,255,255,0.12)" {...ringStyle} />
        <circle cx={CX} cy={CY} r={R_MID} stroke="rgba(255,255,255,0.08)" {...ringStyle} />
        <circle cx={CX} cy={CY} r={R_INNER} stroke="rgba(255,255,255,0.06)" {...ringStyle} />

        {/* Ring fills for zones */}
        <circle cx={CX} cy={CY} r={R_INNER} fill="rgba(255,255,255,0.04)" />
        <circle cx={CX} cy={CY} r={R_MID} fill="rgba(255,255,255,0.02)" style={{ mixBlendMode: "screen" }} />

        {/* Cross-hairs */}
        <line x1={CX - R_OUTER} y1={CY} x2={CX + R_OUTER} y2={CY} stroke="rgba(255,255,255,0.15)" strokeWidth={1} />
        <line x1={CX} y1={CY - R_OUTER} x2={CX} y2={CY + R_OUTER} stroke="rgba(255,255,255,0.15)" strokeWidth={1} />

        {/* Axis labels */}
        <text x={CX} y={CY - R_OUTER - 8} textAnchor="middle" fill="rgba(255,255,255,0.6)" fontSize="10" fontWeight="700" letterSpacing="0.05em">
          IMPLIED VOL
        </text>

        <text x={CX + R_OUTER + 6} y={CY + 4} textAnchor="start" fill="rgba(255,255,255,0.5)" fontSize="9" fontWeight="600">
          SPOT
        </text>

        {/* Outer quadrant labels */}
        <text x={CX - R_MID - 15} y={CY - R_MID - 10} textAnchor="middle" fill="rgba(255,255,255,0.5)" fontSize="9" fontWeight="600">
          SELL PUT
        </text>
        <text x={CX + R_MID + 15} y={CY - R_MID - 10} textAnchor="middle" fill="rgba(255,255,255,0.5)" fontSize="9" fontWeight="600">
          SELL CALL
        </text>
        <text x={CX - R_MID - 15} y={CY + R_MID + 18} textAnchor="middle" fill="rgba(255,255,255,0.5)" fontSize="9" fontWeight="600">
          BUY CALL
        </text>
        <text x={CX + R_MID + 15} y={CY + R_MID + 18} textAnchor="middle" fill="rgba(255,255,255,0.5)" fontSize="9" fontWeight="600">
          BUY PUT
        </text>

        {/* Top/bottom strategy labels */}
        <text x={CX} y={CY - R_MID + 15} textAnchor="middle" fill="rgba(255,255,255,0.35)" fontSize="8" fontWeight="600">
          SELL STRADDLE/
        </text>
        <text x={CX} y={CY - R_MID + 24} textAnchor="middle" fill="rgba(255,255,255,0.35)" fontSize="8" fontWeight="600">
          STRANGLE
        </text>

        <text x={CX} y={CY + R_MID - 10} textAnchor="middle" fill="rgba(255,255,255,0.35)" fontSize="8" fontWeight="600">
          BUY STRADDLE/
        </text>
        <text x={CX} y={CY + R_MID - 1} textAnchor="middle" fill="rgba(255,255,255,0.35)" fontSize="8" fontWeight="600">
          STRANGLE
        </text>

        {/* Left/right strategy labels */}
        <text x={CX - R_MID + 5} y={CY - 6} textAnchor="middle" fill="rgba(255,255,255,0.35)" fontSize="7.5" fontWeight="600">
          BULLISH RISK
        </text>
        <text x={CX - R_MID + 5} y={CY + 3} textAnchor="middle" fill="rgba(255,255,255,0.35)" fontSize="7.5" fontWeight="600">
          REVERSAL
        </text>

        <text x={CX + R_MID - 5} y={CY - 6} textAnchor="middle" fill="rgba(255,255,255,0.35)" fontSize="7.5" fontWeight="600">
          BEARISH RISK
        </text>
        <text x={CX + R_MID - 5} y={CY + 3} textAnchor="middle" fill="rgba(255,255,255,0.35)" fontSize="7.5" fontWeight="600">
          REVERSAL
        </text>

        {/* Inner ring spread labels */}
        <text x={CX - 30} y={CY - R_INNER + 18} textAnchor="middle" fill="rgba(255,255,255,0.25)" fontSize="7">
          SELL PUT
        </text>
        <text x={CX - 30} y={CY - R_INNER + 26} textAnchor="middle" fill="rgba(255,255,255,0.25)" fontSize="7">
          SPREAD
        </text>

        <text x={CX + 30} y={CY - R_INNER + 18} textAnchor="middle" fill="rgba(255,255,255,0.25)" fontSize="7">
          SELL CALL
        </text>
        <text x={CX + 30} y={CY - R_INNER + 26} textAnchor="middle" fill="rgba(255,255,255,0.25)" fontSize="7">
          SPREAD
        </text>

        <text x={CX - 30} y={CY + R_INNER - 12} textAnchor="middle" fill="rgba(255,255,255,0.25)" fontSize="7">
          BUY CALL
        </text>
        <text x={CX - 30} y={CY + R_INNER - 4} textAnchor="middle" fill="rgba(255,255,255,0.25)" fontSize="7">
          SPREAD
        </text>

        <text x={CX + 30} y={CY + R_INNER - 12} textAnchor="middle" fill="rgba(255,255,255,0.25)" fontSize="7">
          BUY PUT
        </text>
        <text x={CX + 30} y={CY + R_INNER - 4} textAnchor="middle" fill="rgba(255,255,255,0.25)" fontSize="7">
          SPREAD
        </text>

        {/* Markers */}
        {!loading && lastMonth && (() => {
          const pos = markerPos(lastMonth);
          return <CrossMark x={pos.x} y={pos.y} size={7} color="rgba(255,255,255,0.4)" glow filterId="glow-month" />;
        })()}
        {!loading && lastWeek && (() => {
          const pos = markerPos(lastWeek);
          return <CrossMark x={pos.x} y={pos.y} size={10} color="rgba(255,255,255,0.6)" glow filterId="glow-week" />;
        })()}
        {!loading && current && (() => {
          const pos = markerPos(current);
          return (
            <g>
              <CrossMark x={pos.x} y={pos.y} size={14} color="#22c55e" glow filterId="glow-green" />
              <text
                x={pos.x}
                y={pos.y + 22}
                textAnchor="middle"
                fill="#22c55e"
                fontSize="8"
                fontWeight="700"
                filter="url(#glow-green)"
              >
                {strategy}
              </text>
            </g>
          );
        })()}

        {/* Axis percentile indicators */}
        {!loading && current && (
          <>
            {/* IV percentile on right side of vertical axis */}
            <text x={CX + 8} y={CY - R_OUTER + 14} textAnchor="start" fill="rgba(255,255,255,0.4)" fontSize="8">
              IV Pctl: {current.ivPct.toFixed(0)}%
            </text>
            {/* Spot percentile on bottom of horizontal axis */}
            <text x={CX + R_OUTER - 5} y={CY + 14} textAnchor="end" fill="rgba(255,255,255,0.4)" fontSize="8">
              Spot Pctl: {current.spotPct.toFixed(0)}%
            </text>
          </>
        )}

        {/* Loading state */}
        {loading && (
          <text x={CX} y={CY} textAnchor="middle" fill="rgba(255,255,255,0.3)" fontSize="12">
            Loading...
          </text>
        )}
      </svg>

      {/* Legend */}
      <div className="flex items-center gap-4 text-[10px] text-white/50">
        <span className="flex items-center gap-1">
          <svg width="10" height="10"><line x1="1" y1="1" x2="9" y2="9" stroke="rgba(255,255,255,0.3)" strokeWidth="1.5" /><line x1="9" y1="1" x2="1" y2="9" stroke="rgba(255,255,255,0.3)" strokeWidth="1.5" /></svg>
          LAST MONTH
        </span>
        <span className="flex items-center gap-1">
          <svg width="12" height="12"><line x1="1" y1="1" x2="11" y2="11" stroke="rgba(255,255,255,0.5)" strokeWidth="2" /><line x1="11" y1="1" x2="1" y2="11" stroke="rgba(255,255,255,0.5)" strokeWidth="2" /></svg>
          LAST WEEK
        </span>
        <span className="flex items-center gap-1">
          <svg width="14" height="14"><line x1="1" y1="1" x2="13" y2="13" stroke="#22c55e" strokeWidth="2.5" /><line x1="13" y1="1" x2="1" y2="13" stroke="#22c55e" strokeWidth="2.5" /></svg>
          CURRENT
        </span>
      </div>

      {/* Metrics */}
      <div className="flex flex-wrap items-center justify-center gap-x-5 gap-y-2 text-xs">
        <div className="flex items-center gap-1.5">
          <span className="font-semibold uppercase tracking-wider text-white/50">IV</span>
          <span className="font-mono font-bold tabular-nums text-blue-400">
            {currentIV !== null ? `${currentIV.toFixed(1)}%` : "—"}
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="font-semibold uppercase tracking-wider text-white/50">RV</span>
          <span className="font-mono font-bold tabular-nums text-amber-400">
            {rv !== null ? `${rv.toFixed(1)}%` : "—"}
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="font-semibold uppercase tracking-wider text-white/50">Carry</span>
          <span className={`rounded px-1.5 py-0.5 font-mono font-bold tabular-nums ${
            carry !== null && carry >= 0
              ? "bg-green-500/20 text-green-400"
              : "bg-red-500/20 text-red-400"
          }`}>
            {carry !== null ? carry.toFixed(2) : "—"}
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="font-semibold uppercase tracking-wider text-white/50">IV Pctl</span>
          <span className="rounded bg-blue-500/20 px-1.5 py-0.5 font-mono font-bold tabular-nums text-blue-400">
            {ivPercentile !== null ? `${ivPercentile.toFixed(1)}%` : "—"}
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="font-semibold uppercase tracking-wider text-white/50">Spot Pctl</span>
          <span className="rounded bg-purple-500/20 px-1.5 py-0.5 font-mono font-bold tabular-nums text-purple-400">
            {current ? `${current.spotPct.toFixed(1)}%` : "—"}
          </span>
        </div>
      </div>
    </div>
  );
}
