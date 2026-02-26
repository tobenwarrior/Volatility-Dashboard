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

interface IvChartProps {
  data: HistoryPoint[];
  tenor: string;
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

export default function IvChart({ data, tenor }: IvChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const ivSeriesRef = useRef<ISeriesApi<SeriesType> | null>(null);
  const rrSeriesRef = useRef<ISeriesApi<SeriesType> | null>(null);

  // Create chart once
  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "#161b22" },
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
      leftPriceScale: {
        visible: true,
        borderColor: "rgba(255,255,255,0.08)",
      },
      width: containerRef.current.clientWidth,
      height: 350,
    });

    const ivSeries = chart.addSeries(LineSeries, {
      color: IV_COLOR,
      lineWidth: 2,
      lineStyle: LineStyle.Solid,
      crosshairMarkerVisible: true,
      lastValueVisible: false,
      priceLineVisible: false,
      priceScaleId: "left",
      priceFormat: {
        type: "custom",
        formatter: (p: number) => p.toFixed(2) + "%",
      },
    });

    const rrSeries = chart.addSeries(LineSeries, {
      color: RR_COLOR,
      lineWidth: 2,
      lineStyle: LineStyle.Solid,
      crosshairMarkerVisible: true,
      lastValueVisible: false,
      priceLineVisible: false,
      priceScaleId: "right",
      priceFormat: {
        type: "custom",
        formatter: (p: number) => p.toFixed(2),
      },
    });

    chartRef.current = chart;
    ivSeriesRef.current = ivSeries;
    rrSeriesRef.current = rrSeries;

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
      ivSeriesRef.current = null;
      rrSeriesRef.current = null;
    };
  }, []);

  // Update data
  useEffect(() => {
    if (!chartRef.current || !ivSeriesRef.current || !rrSeriesRef.current) return;

    ivSeriesRef.current.setData(toLineData(data, "atm_iv"));
    rrSeriesRef.current.setData(toLineData(data, "rr_25d"));
    chartRef.current.timeScale().fitContent();
  }, [data]);

  return (
    <div>
      <div className="mb-3 flex items-center gap-5 text-[11px]">
        <span className="text-xs font-medium uppercase tracking-wider text-deribit-gray">
          {tenor}
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-4 rounded" style={{ backgroundColor: IV_COLOR }} />
          <span style={{ color: IV_COLOR }}>ATM IV (%)</span>
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-4 rounded" style={{ backgroundColor: RR_COLOR }} />
          <span style={{ color: RR_COLOR }}>25&Delta; RR</span>
        </span>
      </div>
      <div ref={containerRef} className="w-full rounded-lg overflow-hidden" />
    </div>
  );
}
