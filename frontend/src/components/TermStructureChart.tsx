"use client";

import { useId, useState } from "react";
import { TenorData, TimeRange } from "@/types";

interface TermStructureChartProps {
  tenors: TenorData[] | undefined;
  changeRange?: TimeRange;
}

const PLOT = { top: 30, right: 50, bottom: 40, left: 50 };
const SVG_W = 600;
const SVG_H = 280;
const PLOT_W = SVG_W - PLOT.left - PLOT.right;
const PLOT_H = SVG_H - PLOT.top - PLOT.bottom;
const BAR_W = 20;

const C = {
  blue: "#4d8dff",
  green: "#21c97e",
  red: "#f74a73",
  gray: "#8b95a5",
  grid: "rgba(255,255,255,0.06)",
  zero: "rgba(255,255,255,0.15)",
  greenBar: "rgba(33,201,126,0.45)",
  redBar: "rgba(247,74,115,0.45)",
  bg: "#161b22",
};

function niceScale(min: number, max: number, ticks: number) {
  // Guard: if range is zero or negligible, force a safe range
  if (!isFinite(min) || !isFinite(max) || max - min < 1e-9) {
    const mid = isFinite(min) ? min : 0;
    min = mid - 2;
    max = mid + 2;
  }

  const range = max - min;
  const rough = range / Math.max(ticks - 1, 1);

  // Safe magnitude calculation
  const logVal = Math.log10(Math.max(rough, 1e-12));
  const mag = Math.pow(10, Math.floor(logVal));
  const nice = ([1, 2, 2.5, 5, 10].find((n) => n * mag >= rough) ?? 10) * mag;

  // Guard against zero/tiny step size
  if (nice < 1e-12) {
    return { min: min - 2, max: max + 2, ticks: [min - 2, min, max, max + 2] };
  }

  const lo = Math.floor(min / nice) * nice;
  const hi = Math.ceil(max / nice) * nice;
  const vals: number[] = [];

  // Safety cap: never generate more than 20 ticks
  const maxIter = 20;
  for (let v = lo, count = 0; v <= hi + nice * 0.01 && count < maxIter; v += nice, count++) {
    vals.push(parseFloat(v.toFixed(6)));
  }

  // Must have at least 2 ticks
  if (vals.length < 2) {
    return { min: lo, max: hi, ticks: [lo, hi] };
  }

  return { min: lo, max: hi, ticks: vals };
}

function symScale(values: number[], tickCount: number) {
  if (values.length === 0) {
    return { min: -1, max: 1, ticks: [-1, 0, 1] };
  }
  const abs = Math.max(...values.map((v) => Math.abs(v)), 0.01);
  const padded = abs * 1.3;
  return niceScale(-padded, padded, tickCount);
}

export default function TermStructureChart({ tenors, changeRange = "24H" }: TermStructureChartProps) {
  // Hover tracks tenor label (stable across re-renders), not index
  const [hoveredLabel, setHoveredLabel] = useState<string | null>(null);
  const clipId = useId();
  const valid = (tenors ?? []).filter((t) => t.atm_iv != null);

  if (valid.length < 2) {
    return (
      <p className="py-10 text-center text-sm text-white/40">
        {tenors === undefined ? "Loading..." : "Not enough IV data to chart."}
      </p>
    );
  }

  const ivs = valid.map((t) => t.atm_iv!);
  const changes = valid.map((t) => t.iv_change ?? t.dod_iv_change);
  const hasChanges = changes.some((c) => c != null);
  const changeVals = changes.filter((c): c is number => c != null);

  // Resolve hovered index from label (safe across data updates)
  const hoveredIdx = hoveredLabel !== null
    ? valid.findIndex((t) => t.label === hoveredLabel)
    : -1;
  const hovered = hoveredIdx >= 0 ? hoveredIdx : null;

  // Scales
  const ivRange = Math.max(Math.max(...ivs) - Math.min(...ivs), 0.01);
  const ivScale = niceScale(
    Math.min(...ivs) - ivRange * 0.15,
    Math.max(...ivs) + ivRange * 0.15,
    5
  );
  const chgScale = hasChanges
    ? symScale(changeVals, 5)
    : { min: -1, max: 1, ticks: [-1, 0, 1] };

  // Mapping helpers — points evenly spaced with half-step padding on each side
  // so edge bars never overflow the plot area
  const step = PLOT_W / valid.length;
  const xPos = (i: number) => PLOT.left + step / 2 + i * step;

  const ivDenom = ivScale.max - ivScale.min;
  const chgDenom = chgScale.max - chgScale.min;

  const yIv = (v: number) =>
    PLOT.top + PLOT_H - ((v - ivScale.min) / (ivDenom || 1)) * PLOT_H;
  const yChg = (v: number) =>
    PLOT.top + PLOT_H - ((v - chgScale.min) / (chgDenom || 1)) * PLOT_H;

  const zeroY = yChg(0);

  // IV polyline path
  const linePts = valid.map((_, i) => `${xPos(i)},${yIv(ivs[i])}`).join(" ");

  // Curve shape
  const first = ivs[0];
  const last = ivs[ivs.length - 1];
  const shape =
    Math.abs(first - last) < 0.3
      ? "Flat"
      : first < last
        ? "Contango"
        : "Backwardation";

  return (
    <div>
      <svg
        viewBox={`0 0 ${SVG_W} ${SVG_H}`}
        preserveAspectRatio="xMidYMid meet"
        className="w-full"
        role="img"
        aria-label="IV Term Structure chart"
      >
        {/* Clip path to contain bars and line within plot area */}
        <defs>
          <clipPath id={clipId}>
            <rect
              x={PLOT.left}
              y={PLOT.top}
              width={PLOT_W}
              height={PLOT_H}
            />
          </clipPath>
        </defs>

        {/* Grid lines */}
        {ivScale.ticks.map((t) => (
          <line
            key={`g-${t}`}
            x1={PLOT.left}
            x2={SVG_W - PLOT.right}
            y1={yIv(t)}
            y2={yIv(t)}
            stroke={C.grid}
            strokeWidth={1}
          />
        ))}

        {/* Zero line for change axis */}
        {hasChanges && (
          <line
            x1={PLOT.left}
            x2={SVG_W - PLOT.right}
            y1={zeroY}
            y2={zeroY}
            stroke={C.zero}
            strokeWidth={1}
            strokeDasharray="4 4"
          />
        )}

        {/* Clipped content: bars + line + dots */}
        <g clipPath={`url(#${clipId})`}>
          {/* IV Change bars with hover */}
          {hasChanges &&
            valid.map((t, i) => {
              const c = t.iv_change ?? t.dod_iv_change;
              if (c == null) return null;
              const barTop = c >= 0 ? yChg(c) : zeroY;
              const barH = Math.abs(yChg(c) - zeroY);
              return (
                <g key={`bar-${t.label}`}>
                  <rect
                    x={xPos(i) - BAR_W / 2}
                    y={barTop}
                    width={BAR_W}
                    height={Math.max(barH, 1)}
                    rx={3}
                    fill={c >= 0 ? C.greenBar : C.redBar}
                    style={{ transition: "opacity 0.15s" }}
                    opacity={hovered === null || hovered === i ? 1 : 0.3}
                  />
                  {/* Invisible wider hit area for easier hover */}
                  <rect
                    x={xPos(i) - BAR_W}
                    y={PLOT.top}
                    width={BAR_W * 2}
                    height={PLOT_H}
                    fill="transparent"
                    onMouseEnter={() => setHoveredLabel(t.label)}
                    onMouseLeave={() => setHoveredLabel(null)}
                    style={{ cursor: "crosshair" }}
                  />
                </g>
              );
            })}

          {/* IV line */}
          <polyline
            points={linePts}
            fill="none"
            stroke={C.blue}
            strokeWidth={2}
          />

          {/* IV dots */}
          {valid.map((t, i) => (
            <circle
              key={`dot-${t.label}`}
              cx={xPos(i)}
              cy={yIv(ivs[i])}
              r={4}
              fill={C.blue}
              stroke={C.bg}
              strokeWidth={2}
            />
          ))}
        </g>

        {/* Hover tooltip for IV change — OUTSIDE clipPath so it's never cut off */}
        {hovered !== null && (valid[hovered]?.iv_change ?? valid[hovered]?.dod_iv_change) != null && (() => {
          const c = (valid[hovered].iv_change ?? valid[hovered].dod_iv_change)!;
          const label = valid[hovered].label;
          const tx = xPos(hovered);
          // Position tooltip above bar if positive, below if negative
          // Clamp within SVG bounds
          const rawTy = c >= 0 ? yChg(c) - 8 : yChg(c) + 16;
          const ty = Math.max(14, Math.min(rawTy, SVG_H - 4));
          return (
            <g>
              <rect
                x={tx - 32}
                y={ty - 12}
                width={64}
                height={18}
                rx={4}
                fill="rgba(0,0,0,0.8)"
              />
              <text
                x={tx}
                y={ty}
                textAnchor="middle"
                fill={c >= 0 ? C.green : C.red}
                fontSize={10}
                fontWeight={600}
              >
                {label} {c > 0 ? "+" : ""}{c.toFixed(2)}%
              </text>
            </g>
          );
        })()}

        {/* Value labels above dots */}
        {valid.map((t, i) => (
          <text
            key={`lbl-${t.label}`}
            x={xPos(i)}
            y={yIv(ivs[i]) - 10}
            textAnchor="middle"
            fill={C.gray}
            fontSize={10}
          >
            {ivs[i].toFixed(1)}%
          </text>
        ))}

        {/* Left y-axis labels (ATM IV) — only top and bottom to avoid overlap with dot labels */}
        {(() => {
          const first = ivScale.ticks[0];
          const last = ivScale.ticks[ivScale.ticks.length - 1];
          const labels = first === last ? [first] : [first, last];
          return labels.map((t, i) => (
            <text
              key={`ly-${i}`}
              x={PLOT.left - 8}
              y={yIv(t) + 3}
              textAnchor="end"
              fill={C.gray}
              fontSize={10}
            >
              {t.toFixed(1)}%
            </text>
          ));
        })()}

        {/* Right y-axis labels (IV Change) */}
        {hasChanges &&
          chgScale.ticks.map((t) => (
            <text
              key={`ry-${t}`}
              x={SVG_W - PLOT.right + 8}
              y={yChg(t) + 3}
              textAnchor="start"
              fill={C.gray}
              fontSize={10}
            >
              {t > 0 ? "+" : ""}
              {t.toFixed(1)}
            </text>
          ))}

        {/* X-axis tenor labels */}
        {valid.map((t, i) => (
          <text
            key={`x-${t.label}`}
            x={xPos(i)}
            y={SVG_H - PLOT.bottom + 20}
            textAnchor="middle"
            fill={C.gray}
            fontSize={11}
            fontWeight={500}
          >
            {t.label}
          </text>
        ))}

        {/* Axis titles */}
        <text
          x={12}
          y={PLOT.top + PLOT_H / 2}
          textAnchor="middle"
          fill="rgba(255,255,255,0.3)"
          fontSize={9}
          transform={`rotate(-90, 12, ${PLOT.top + PLOT_H / 2})`}
        >
          ATM IV (%)
        </text>
        {hasChanges && (
          <text
            x={SVG_W - 8}
            y={PLOT.top + PLOT_H / 2}
            textAnchor="middle"
            fill="rgba(255,255,255,0.3)"
            fontSize={9}
            transform={`rotate(90, ${SVG_W - 8}, ${PLOT.top + PLOT_H / 2})`}
          >
            {changeRange} Chg (%)
          </text>
        )}
      </svg>

      {/* Legend */}
      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px]">
        <span className="flex items-center gap-1.5">
          <span
            className="inline-block h-0.5 w-4 rounded"
            style={{ backgroundColor: C.blue }}
          />
          <span style={{ color: C.blue }}>ATM IV</span>
        </span>
        {hasChanges && (
          <>
            <span className="flex items-center gap-1.5">
              <span
                className="inline-block h-3 w-3 rounded-sm"
                style={{ backgroundColor: C.greenBar }}
              />
              <span className="text-deribit-green">IV Up</span>
            </span>
            <span className="flex items-center gap-1.5">
              <span
                className="inline-block h-3 w-3 rounded-sm"
                style={{ backgroundColor: C.redBar }}
              />
              <span className="text-deribit-red">IV Down</span>
            </span>
          </>
        )}
        <span className="text-white/30">&middot;</span>
        <span className="text-white/40">{shape}</span>
      </div>
    </div>
  );
}
