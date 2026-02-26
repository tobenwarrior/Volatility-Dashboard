"use client";

import { useTenors } from "@/hooks/useTenors";
import { usePrice } from "@/hooks/usePrice";
import StatusBadge from "@/components/StatusBadge";
import PriceTicker from "@/components/PriceTicker";
import TenorTable from "@/components/TenorTable";

export default function Home() {
  const { data, error, isLoading } = useTenors();
  const { price, prevPrice } = usePrice();

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col items-center gap-10 px-6 py-16">
      <div className="flex w-full items-center justify-between">
        <h1 className="text-lg font-semibold tracking-tight text-white">
          BTC Volatility Estimator
        </h1>
        <StatusBadge isLoading={isLoading} error={error} />
      </div>

      <PriceTicker price={price} prevPrice={prevPrice} />

      <div className="w-full rounded-xl border border-white/[0.08] bg-surface-raised p-6">
        <h2 className="mb-5 text-sm font-medium uppercase tracking-wider text-deribit-gray">
          Implied Volatility Term Structure
        </h2>
        <TenorTable tenors={data?.tenors} />
      </div>

      {data?.timestamp && (
        <p className="text-xs text-white/40">Last updated: {data.timestamp}</p>
      )}
    </main>
  );
}
