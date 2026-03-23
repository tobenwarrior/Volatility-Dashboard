import { TenorLabel } from "@/types";

const TENORS: TenorLabel[] = ["1W", "2W", "30D", "60D", "90D", "180D"];

interface TenorSelectorProps {
  selected: TenorLabel;
  onChange: (tenor: TenorLabel) => void;
}

export default function TenorSelector({ selected, onChange }: TenorSelectorProps) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-[10px] font-medium uppercase tracking-wider text-white/30">Tenor</span>
      {TENORS.map((t) => (
        <button
          key={t}
          onClick={() => onChange(t)}
          className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
            t === selected
              ? "bg-deribit-blue text-white"
              : "bg-white/[0.06] text-deribit-gray hover:bg-white/[0.1] hover:text-white"
          }`}
        >
          {t}
        </button>
      ))}
    </div>
  );
}
