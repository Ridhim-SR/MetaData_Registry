export function Skeleton({ className = "" }: { className?: string }) {
  return (
    <div
      aria-hidden
      className={`animate-pulse rounded-md ${className}`}
      style={{ background: "var(--border)" }}
    />
  );
}

export function LoadingBlock({ lines = 3 }: { lines?: number }) {
  return (
    <div role="status" aria-label="Loading" className="space-y-2">
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton key={i} className="h-4 w-full" />
      ))}
      <span className="sr-only">Loading…</span>
    </div>
  );
}

export function ErrorBlock({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div
      role="alert"
      className="rounded-md px-4 py-3 text-sm"
      style={{
        border: "1px solid var(--confid-fg)",
        background: "var(--confid-bg)",
        color: "var(--confid-fg)",
        borderRadius: 6,
      }}
    >
      <p>{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="btn-secondary mt-2"
          style={{ padding: "0.25rem 0.75rem", fontSize: "0.875rem" }}
        >
          Retry
        </button>
      )}
    </div>
  );
}

/**
 * Short, friendly empty state: one or two lines of text plus a single action.
 * No large dashed boxes (GIGW minimalist style).
 */
export function EmptyBlock({
  title,
  body,
  action,
}: {
  title: string;
  body?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="py-2">
      <p className="text-sm font-semibold" style={{ color: "var(--text)" }}>
        {title}
      </p>
      {body && (
        <p className="mt-1 max-w-xl text-sm" style={{ color: "var(--text-muted)" }}>
          {body}
        </p>
      )}
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}

export function friendlyError(status: number | undefined, fallback: string): string {
  if (status === 0) return "Unable to reach the server. Check your connection and try again.";
  return fallback;
}
