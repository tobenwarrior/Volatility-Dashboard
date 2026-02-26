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
}

function toLineData(
  raw: HistoryPoint[],
  field: "atm_iv" | "rr_25d"
): LineData<UTCTimestamp>[] {
  const out: LineData<UTCTimestamp>[] = [];
  for (const point of raw) {
    const value = point[field];
    if (value == null) continue;
    out.push({ time: point.time as UTCTimestamp, value });
  }
  return out;
}

const IV_COLOR = "#4d8dff";
const RR_COLOR = "#21c97e";
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
}: {
  data: HistoryPoint[];
  field: "atm_iv" | "rr_25d";
  color: string;
  label: string;
  formatter: (p: number) => string;
  height: number;
  t1Value: number | null;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<SeriesType> | null>(null);
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
    };
  }, [color, formatter, height]);

  // Update data + T-1 reference line
  useEffect(() => {
    if (!chartRef.current || !seriesRef.current) return;

    const lineData = toLineData(data, field);
    seriesRef.current.setData(lineData);

    // Remove previous T-1 line before adding a new one
    if (priceLineRef.current && seriesRef.current) {
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
            <span className="text-white/40">T-1 ({formatter(t1Value)})</span>
          </span>
        )}
      </div>
      <div ref={containerRef} className="w-full rounded-lg overflow-hidden" />
    </div>
  );
}

const ivFormatter = (p: number) => p.toFixed(2) + "%";
const rrFormatter = (p: number) => p.toFixed(2);

export default function IvChart({ data, tenor, tenorData }: IvChartProps) {
  // Compute T-1 values: current value minus the DoD change = value 24h ago
  const ivT1 =
    tenorData?.atm_iv != null && tenorData?.dod_iv_change != null
      ? tenorData.atm_iv - tenorData.dod_iv_change
      : null;
  const rrT1 =
    tenorData?.rr_25d != null && tenorData?.dod_rr_change != null
      ? tenorData.rr_25d - tenorData.dod_rr_change
      : null;

  return (
    <div className="space-y-4">
      <div className="flex items-center text-xs font-medium uppercase tracking-wider text-deribit-gray">
        {tenor}
      </div>
      <SingleChart
        data={data}
        field="atm_iv"
        color={IV_COLOR}
        label="ATM IV (%)"
        formatter={ivFormatter}
        height={200}
        t1Value={ivT1}
      />
      <SingleChart
        data={data}
        field="rr_25d"
        color={RR_COLOR}
        label="25&Delta; RR"
        formatter={rrFormatter}
        height={200}
        t1Value={rrT1}
      />
    </div>
  );
}
