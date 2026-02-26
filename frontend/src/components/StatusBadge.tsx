interface StatusBadgeProps {
  isLoading: boolean;
  error: string | null;
}

export default function StatusBadge({ isLoading, error }: StatusBadgeProps) {
  if (isLoading) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-yellow-500/20 px-3 py-1 text-xs font-medium text-yellow-400">
        <span className="h-2 w-2 animate-pulse rounded-full bg-yellow-400" />
        Connecting
      </span>
    );
  }

  if (error) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-deribit-red/20 px-3 py-1 text-xs font-medium text-deribit-red">
        <span className="h-2 w-2 rounded-full bg-deribit-red" />
        Error
      </span>
    );
  }

  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-deribit-green/20 px-3 py-1 text-xs font-medium text-deribit-green">
      <span className="h-2 w-2 animate-pulse rounded-full bg-deribit-green" />
      LIVE
    </span>
  );
}
