"use client";

import { useEffect, useRef } from "react";
import {
  createChart,
  ColorType,
  LineStyle,
  LineSeries,
  type IChartApi,
  type ISeriesApi,
  type SeriesType,
  type UTCTimestamp,
  type LineData,
} from "lightweight-charts";
import { HistoryPoint } from "@/types";
import { type RVPoint } from "@/hooks/useRVSeries";

interface IvChartProps {
  data: HistoryPoint[];
  tenor: string;
  resetCounter?: number;
  showIV?: boolean;
  showRV?: boolean;
  showCarry?: boolean;
  rvData?: RVPoint[];
}

const SGT_OFFSET = 8 * 3600; // UTC+8

function toLineData(
  raw: HistoryPoint[],
  field: "atm_iv" | "rr_25d"
): LineData<UTCTimestamp>[] {
  const out: LineData<UTCTimestamp>[] = [];
  let prevTime = -1;
  for (const point of raw) {
    const value = point[field];
    if (value == null) continue;
    const t = point.time + SGT_OFFSET;
    if (t <= prevTime) continue;
    prevTime = t;
    out.push({ time: t as UTCTimestamp, value });
  }
  return out;
}

function rvToLineData(raw: RVPoint[], ivData: HistoryPoint[]): LineData<UTCTimestamp>[] {
  const out: LineData<UTCTimestamp>[] = [];
  let prevTime = -1;
  for (const point of raw) {
    const t = point.time + SGT_OFFSET;
    if (t <= prevTime) continue;
    prevTime = t;
    out.push({ time: t as UTCTimestamp, value: point.rv });
  }
  // If only 1 point, stretch it across the IV data range as a flat line
  if (out.length === 1 && ivData.length > 1) {
    const rv = out[0].value;
    const firstIV = ivData[0].time + SGT_OFFSET;
    const lastIV = ivData[ivData.length - 1].time + SGT_OFFSET;
    return [
      { time: firstIV as UTCTimestamp, value: rv },
      { time: lastIV as UTCTimestamp, value: rv },
    ];
  }
  return out;
}

const IV_COLOR = "#4d8dff";
const RR_COLOR = "#21c97e";
const RV_COLOR = "#f59e0b";
const CARRY_COLOR = "#a78bfa"; // purple
const T1_COLOR = "rgba(255, 255, 255, 0.25)";

/** Compute carry (IV - RV) line data. */
function computeCarryLineData(
  ivData: HistoryPoint[],
  rvLineData: LineData<UTCTimestamp>[]
): { carryData: LineData<UTCTimestamp>[] } {
  const carryData: LineData<UTCTimestamp>[] = [];
  if (ivData.length === 0 || rvLineData.length === 0) return { carryData };

  const rvMap = new Map<number, number>();
  for (const pt of rvLineData) {
    rvMap.set(pt.time as number, pt.value);
  }

  let prevTime = -1;
  for (const point of ivData) {
    if (point.atm_iv == null) continue;
    const t = point.time + SGT_OFFSET;
    if (t <= prevTime) continue;
    prevTime = t;

    const hourFloor = t - (t % 3600);
    const rvVal = rvMap.get(hourFloor) ?? rvMap.get(hourFloor - 3600) ?? rvMap.get(hourFloor + 3600);
    if (rvVal !== undefined) {
      carryData.push({ time: t as UTCTimestamp, value: Math.round((point.atm_iv - rvVal) * 100) / 100 });
    }
  }

  // If only 1 RV point (1H range), use it for all IV points
  if (carryData.length <= 1 && rvLineData.length >= 1) {
    const singleRV = rvLineData[0].value;
    carryData.length = 0;
    let prev = -1;
    for (const point of ivData) {
      if (point.atm_iv == null) continue;
      const t = point.time + SGT_OFFSET;
      if (t <= prev) continue;
      prev = t;
      carryData.push({ time: t as UTCTimestamp, value: Math.round((point.atm_iv - singleRV) * 100) / 100 });
    }
  }

  return { carryData };
}

const CHART_OPTIONS = {
  layout: {
    background: { type: ColorType.Solid as const, color: "#161b22" },
    textColor: "#8b95a5",
    fontSize: 11,
  },
  grid: {
    vertLines: { color: "rgba(255,255,255,0.04)" },
    horzLines: { color: "rgba(255,255,255,0.04)" },
  },
  crosshair: {
    vertLine: { color: "rgba(255,255,255,0.1)", labelBackgroundColor: "#2d333b" },
    horzLine: { color: "rgba(255,255,255,0.1)", labelBackgroundColor: "#2d333b" },
  },
  timeScale: {
    timeVisible: true,
    secondsVisible: false,
    borderColor: "rgba(255,255,255,0.08)",
  },
  rightPriceScale: {
    borderColor: "rgba(255,255,255,0.08)",
  },
};

function SingleChart({
  data,
  field,
  color,
  label,
  formatter,
  height,
  t1Value,
  resetCounter,
  rvLineData,
  overrideLineData,
  overlayColor,
  overlayLabel,
  showOverlay,
  hideMainLine,
}: {
  data: HistoryPoint[];
  field: "atm_iv" | "rr_25d";
  color: string;
  label: string;
  formatter: (p: number) => string;
  height: number;
  t1Value: number | null;
  resetCounter: number;
  rvLineData?: LineData<UTCTimestamp>[];
  overrideLineData?: LineData<UTCTimestamp>[];
  overlayColor?: string;
  overlayLabel?: string;
  showOverlay?: boolean;
  hideMainLine?: boolean;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<SeriesType> | null>(null);
  const overlaySeriesRef = useRef<ISeriesApi<SeriesType> | null>(null);
  const priceLineRef = useRef<ReturnType<ISeriesApi<SeriesType>["createPriceLine"]> | null>(null);

  // Create chart once
  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      ...CHART_OPTIONS,
      leftPriceScale: { visible: false, borderColor: "rgba(255,255,255,0.08)" },
      width: containerRef.current.clientWidth,
      height,
    });

    const series = chart.addSeries(LineSeries, {
      color,
      lineWidth: 2,
      lineStyle: LineStyle.Solid,
      crosshairMarkerVisible: true,
      lastValueVisible: true,
      priceLineVisible: false,
      priceScaleId: "right",
      priceFormat: {
        type: "custom",
        formatter,
      },
    });

    chartRef.current = chart;
    seriesRef.current = series;

    const el = containerRef.current;
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        chart.applyOptions({ width: entry.contentRect.width });
      }
    });
    observer.observe(el);

    return () => {
      observer.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
      overlaySeriesRef.current = null;
    };
  }, [color, formatter, height]);

  // Manage overlay series
  useEffect(() => {
    if (!chartRef.current) return;

    if (showOverlay && !overlaySeriesRef.current && overlayColor) {
      overlaySeriesRef.current = chartRef.current.addSeries(LineSeries, {
        color: overlayColor,
        lineWidth: 2,
        lineStyle: LineStyle.Dashed,
        crosshairMarkerVisible: true,
        lastValueVisible: true,
        priceLineVisible: false,
        priceScaleId: "right",
        priceFormat: {
          type: "custom",
          formatter,
        },
      });
      if (rvLineData && rvLineData.length > 0) {
        overlaySeriesRef.current.setData(rvLineData);
      }
    } else if (!showOverlay && overlaySeriesRef.current) {
      chartRef.current.removeSeries(overlaySeriesRef.current);
      overlaySeriesRef.current = null;
    }
  }, [showOverlay, overlayColor, formatter, rvLineData]);

  // Update overlay data
  useEffect(() => {
    if (!overlaySeriesRef.current || !rvLineData || !showOverlay) return;
    overlaySeriesRef.current.setData(rvLineData);
  }, [rvLineData, showOverlay]);

  // Reset zoom
  useEffect(() => {
    if (resetCounter > 0 && chartRef.current) {
      chartRef.current.timeScale().fitContent();
    }
  }, [resetCounter]);

  // Toggle main line visibility
  useEffect(() => {
    if (!seriesRef.current) return;
    seriesRef.current.applyOptions({
      color: hideMainLine ? "transparent" : color,
      lastValueVisible: !hideMainLine,
      crosshairMarkerVisible: !hideMainLine,
    });
  }, [hideMainLine, color]);

  // Update main data + T-1 reference line
  useEffect(() => {
    if (!chartRef.current || !seriesRef.current) return;

    const lineData = overrideLineData ?? toLineData(data, field);
    seriesRef.current.setData(lineData);

    if (priceLineRef.current) {
      seriesRef.current.removePriceLine(priceLineRef.current);
      priceLineRef.current = null;
    }

    if (t1Value != null) {
      priceLineRef.current = seriesRef.current.createPriceLine({
        price: t1Value,
        color: T1_COLOR,
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: "T-1",
      });
    }

    chartRef.current.timeScale().fitContent();
  }, [data, field, t1Value, overrideLineData]);

  return (
    <div>
      <div className="mb-2 flex items-center gap-3 text-[11px]">
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-4 rounded" style={{ backgroundColor: color }} />
          <span style={{ color }}>{label}</span>
        </span>
        {t1Value != null && (
          <span className="flex items-center gap-1.5">
            <span
              className="inline-block h-0 w-4 border-t border-dashed"
              style={{ borderColor: T1_COLOR }}
            />
            <span className="text-white/40">24h ago ({formatter(t1Value)})</span>
          </span>
        )}
        {showOverlay && overlayColor && overlayLabel && (
          <span className="flex items-center gap-1.5">
            <span
              className="inline-block h-0 w-4 border-t border-dashed"
              style={{ borderColor: overlayColor }}
            />
            <span style={{ color: overlayColor }}>{overlayLabel}</span>
          </span>
        )}
      </div>
      <div ref={containerRef} className="w-full rounded-lg overflow-hidden" />
    </div>
  );
}

const ivFormatter = (p: number) => p.toFixed(2) + "%";
const rrFormatter = (p: number) => p.toFixed(2);

const carryFormatter = (p: number) => (p >= 0 ? "+" : "") + p.toFixed(2);

export default function IvChart({ data, tenor, resetCounter = 0, showIV = true, showRV = false, showCarry = false, rvData = [] }: IvChartProps) {
  const rvLineData = rvToLineData(rvData, data);
  const { carryData } = computeCarryLineData(data, rvLineData);

  return (
    <div className="space-y-4">
      <SingleChart
        data={data}
        field="atm_iv"
        color={IV_COLOR}
        label="ATM IV (%)"
        formatter={ivFormatter}
        height={200}
        t1Value={null}
        resetCounter={resetCounter}
        rvLineData={rvLineData}
        overlayColor={RV_COLOR}
        overlayLabel="RV (%)"
        showOverlay={showRV}
        hideMainLine={!showIV}
      />
      {showCarry && carryData.length > 0 && (
        <SingleChart
          data={data}
          field="atm_iv"
          color={CARRY_COLOR}
          label="Carry (IV&minus;RV)"
          formatter={carryFormatter}
          height={100}
          t1Value={null}
          resetCounter={resetCounter}
          overrideLineData={carryData}
        />
      )}
      <SingleChart
        data={data}
        field="rr_25d"
        color={RR_COLOR}
        label="25&Delta; RR"
        formatter={rrFormatter}
        height={160}
        t1Value={null}
        resetCounter={resetCounter}
      />
    </div>
  );
}
