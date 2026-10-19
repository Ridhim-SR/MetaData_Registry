import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { listDatasets, listPublicDatasets } from "../../api/registry";
import { useAuth } from "../../contexts/AuthContext";
import { hasValidUpdatedAt } from "../../utils/format";
import { DatasetCard } from "./DatasetCard";
import { EmptyBlock, ErrorBlock, Skeleton } from "./StateBlocks";

/**
 * "Recently updated datasets" — signed-in viewers see their whole visible
 * catalog (public datasets alone would hide what they can open). Guests see
 * public datasets when available, otherwise the visible catalog (with access
 * badges), otherwise a single short line of text. No large dashed boxes.
 */
export function PublicDataSection() {
  const { isAuthenticated } = useAuth();
  const pub = useQuery({
    queryKey: ["registry-public"],
    queryFn: listPublicDatasets,
    enabled: !isAuthenticated,
  });
  const showFallback =
    isAuthenticated || Boolean(pub.data && pub.data.items.length === 0 && !pub.error);
  const fallback = useQuery({
    queryKey: ["registry-catalog-recent", isAuthenticated],
    queryFn: () => listDatasets(),
    enabled: showFallback,
    retry: false,
  });

  const items = !isAuthenticated && pub.data && pub.data.items.length > 0 ? pub.data.items.slice(0, 6) : [];
  const fallbackItems = fallback.data ? fallback.data.items.slice(0, 6) : [];
  const shown = items.length > 0 ? items : fallbackItems;
  // Loader on every fetch so stale cards never flash as current.
  const isPending =
    (!isAuthenticated && (pub.isPending || pub.isFetching)) ||
    (showFallback && (fallback.isPending || fallback.isFetching));
  const error = (isAuthenticated ? null : pub.error) ?? (showFallback ? fallback.error : null);
  // Without any valid dates there is nothing "recent" to show.
  const hasAnyDates = shown.some((card) => hasValidUpdatedAt(card.updated_at));
  const heading = hasAnyDates ? "Recently Updated Datasets" : "Latest Datasets";

  return (
    <section
      aria-label={heading}
      style={{ background: "var(--bg)", borderTop: "1px solid var(--border)" }}
    >
      <div className="page-container mx-auto w-full max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
        <div>
          <div
            className="gap-3"
            style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}
          >
            <h2 className="font-semibold" style={{ color: "var(--navy-900)", fontSize: "1.375rem" }}>
              {heading}
            </h2>
            <Link
              to="/explore"
              className="font-semibold"
              style={{ color: "var(--blue-700)", fontSize: "1rem", whiteSpace: "nowrap" }}
            >
              Browse all →
            </Link>
          </div>
          <p className="mt-1 text-sm" style={{ color: "var(--text-muted)", fontSize: "0.9375rem" }}>
            Latest datasets published across departments.
          </p>
        </div>

        {isPending && (
          <div
            className="mt-4"
            style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: "16px" }}
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
          <div
            className="mt-4"
            style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: "16px" }}
          >
            {shown.map((card) => (
              <DatasetCard key={card.dataset} card={card} hideEmptyFields />
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
