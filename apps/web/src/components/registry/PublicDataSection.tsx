import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { listDatasets, listPublicDatasets } from "../../api/registry";
import { DatasetCard } from "./DatasetCard";
import { EmptyBlock, ErrorBlock, Skeleton } from "./StateBlocks";

/**
 * "Recently updated datasets" — shows public datasets when available,
 * otherwise falls back to the caller's visible catalog (with access badges),
 * otherwise a single short line of text. No large dashed boxes.
 */
export function PublicDataSection() {
  const pub = useQuery({ queryKey: ["registry-public"], queryFn: listPublicDatasets });
  const showFallback = Boolean(pub.data && pub.data.items.length === 0 && !pub.error);
  const fallback = useQuery({
    queryKey: ["registry-catalog-recent"],
    queryFn: () => listDatasets(),
    enabled: showFallback,
    retry: false,
  });

  const items = pub.data && pub.data.items.length > 0 ? pub.data.items.slice(0, 6) : [];
  const fallbackItems = fallback.data ? fallback.data.items.slice(0, 6) : [];
  const shown = items.length > 0 ? items : fallbackItems;
  // Loader on every fetch so stale cards never flash as current.
  const isPending =
    pub.isPending ||
    pub.isFetching ||
    (showFallback && (fallback.isPending || fallback.isFetching));
  const error = pub.error ?? (showFallback ? fallback.error : null);

  return (
    <section
      aria-label="Recently updated datasets"
      style={{ background: "var(--bg)", borderTop: "1px solid var(--border)" }}
    >
      <div className="mx-auto w-full max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="font-semibold" style={{ color: "var(--navy-900)", fontSize: "1.375rem" }}>
              Recently Updated Datasets
            </h2>
            <p className="mt-1 text-sm" style={{ color: "var(--text-muted)", fontSize: "0.9375rem" }}>
              Latest datasets published across departments.
            </p>
          </div>
          <Link to="/explore" className="font-semibold" style={{ color: "var(--blue-700)", fontSize: "1rem" }}>
            Browse full catalog →
          </Link>
        </div>

        {isPending && (
          <div
            className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3"
            role="status"
            aria-label="Loading datasets"
          >
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-44" />
            ))}
          </div>
        )}

        {!isPending && error && (
          <div className="mt-4">
            <ErrorBlock
              message="Dataset information is temporarily unavailable."
              onRetry={() => (pub.error ? pub.refetch() : fallback.refetch())}
            />
          </div>
        )}

        {!isPending && !error && shown.length === 0 && (
          <div className="mt-2">
            <EmptyBlock
              title="No datasets published yet."
              body="New datasets will appear here once departments publish them."
              action={
                <Link to="/explore" className="btn-secondary" style={{ fontSize: "0.875rem" }}>
                  Browse Catalog
                </Link>
              }
            />
          </div>
        )}

        {!isPending && !error && shown.length > 0 && (
          <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {shown.map((card) => (
              <DatasetCard key={card.dataset} card={card} />
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
