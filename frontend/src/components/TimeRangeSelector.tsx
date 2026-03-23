import { TimeRange } from "@/types";

const RANGES: TimeRange[] = ["1H", "4H", "24H", "7D", "14D", "30D"];

interface TimeRangeSelectorProps {
  selected: TimeRange;
  onChange: (range: TimeRange) => void;
}

export default function TimeRangeSelector({ selected, onChange }: TimeRangeSelectorProps) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-[10px] font-medium uppercase tracking-wider text-white/30">Range</span>
      {RANGES.map((r) => (
        <button
          key={r}
          onClick={() => onChange(r)}
          className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
            r === selected
              ? "bg-deribit-blue text-white"
              : "bg-white/[0.06] text-deribit-gray hover:bg-white/[0.1] hover:text-white"
          }`}
        >
          {r}
        </button>
      ))}
    </div>
  );
}
