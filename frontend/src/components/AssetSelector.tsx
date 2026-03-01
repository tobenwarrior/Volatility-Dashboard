import { Asset } from "@/types";

const ASSETS: Asset[] = ["BTC", "ETH"];

interface AssetSelectorProps {
  selected: Asset;
  onChange: (asset: Asset) => void;
}

export default function AssetSelector({ selected, onChange }: AssetSelectorProps) {
  return (
    <div className="flex items-center gap-1">
      {ASSETS.map((a) => (
        <button
          key={a}
          onClick={() => onChange(a)}
          className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
            a === selected
              ? "bg-deribit-blue text-white"
              : "bg-white/[0.06] text-deribit-gray hover:bg-white/[0.1] hover:text-white"
          }`}
        >
          {a}
        </button>
      ))}
    </div>
  );
}
