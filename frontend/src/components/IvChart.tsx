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
import { HistoryPoint, TenorData } from "@/types";

interface IvChartProps {
  data: HistoryPoint[];
  tenor: string;
  tenorData?: TenorData;
  resetCounter?: number;
  showRV?: boolean;
}

const SGT_OFFSET = 8 * 3600; // UTC+8

function toLineData(
  raw: HistoryPoint[],
  field: "atm_iv" | "rr_25d" | "rv"
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

const IV_COLOR = "#4d8dff";
const RR_COLOR = "#21c97e";
const RV_COLOR = "#f59e0b";
const T1_COLOR = "rgba(255, 255, 255, 0.25)";

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
  overlayData,
  overlayColor,
  overlayLabel,
  showOverlay,
}: {
  data: HistoryPoint[];
  field: "atm_iv" | "rr_25d";
  color: string;
  label: string;
  formatter: (p: number) => string;
  height: number;
  t1Value: number | null;
  resetCounter: number;
  overlayData?: HistoryPoint[];
  overlayColor?: string;
  overlayLabel?: string;
  showOverlay?: boolean;
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
      leftPriceScale: { visible: false },
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

  // Manage overlay series — add/remove based on showOverlay
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
      // Set data immediately if available
      if (overlayData) {
        overlaySeriesRef.current.setData(toLineData(overlayData, "rv"));
      }
    } else if (!showOverlay && overlaySeriesRef.current) {
      chartRef.current.removeSeries(overlaySeriesRef.current);
      overlaySeriesRef.current = null;
    }
  }, [showOverlay, overlayColor, formatter, overlayData]);

  // Update overlay data when it changes
  useEffect(() => {
    if (!overlaySeriesRef.current || !overlayData || !showOverlay) return;
    overlaySeriesRef.current.setData(toLineData(overlayData, "rv"));
  }, [overlayData, showOverlay]);

  // Reset zoom
  useEffect(() => {
    if (resetCounter > 0 && chartRef.current) {
      chartRef.current.timeScale().fitContent();
    }
  }, [resetCounter]);

  // Update main data + T-1 reference line
  useEffect(() => {
    if (!chartRef.current || !seriesRef.current) return;

    const lineData = toLineData(data, field);
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
  }, [data, field, t1Value]);

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

export default function IvChart({ data, tenor, tenorData, resetCounter = 0, showRV = false }: IvChartProps) {
  // Fill missing historical rv values with the current live rv so the line
  // spans the entire chart immediately (old rows have rv=null in the DB).
  const liveRV = tenorData?.rv ?? null;
  const rvData = liveRV != null
    ? data.map((p) => ({ ...p, rv: p.rv ?? liveRV }))
    : data;

  return (
    <div className="space-y-4">
      <SingleChart
        data={data}
        field="atm_iv"
        color={IV_COLOR}
        label="ATM IV (%)"
        formatter={ivFormatter}
        height={160}
        t1Value={null}
        resetCounter={resetCounter}
        overlayData={rvData}
        overlayColor={RV_COLOR}
        overlayLabel="RV (%)"
        showOverlay={showRV}
      />
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
