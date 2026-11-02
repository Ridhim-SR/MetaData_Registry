import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { getDepartment, searchRegistry } from "../api/registry";
import { humanizeRaw } from "../utils/format";
import { DatasetCard } from "../components/registry/DatasetCard";
import { EmptyBlock, ErrorBlock, LoadingBlock } from "../components/registry/StateBlocks";
import { useAuth } from "../contexts/AuthContext";
import { t, tNodes, useLanguage } from "../i18n";

export function DepartmentDetailPage() {
  useLanguage();
  const { slug = "" } = useParams<{ slug: string }>();
  const [params, setParams] = useSearchParams();
  const within = params.get("q") ?? "";
  const [search, setSearch] = useState(within);
  const { isAuthenticated } = useAuth();

  const deptQuery = useQuery({
    queryKey: ["registry-department", slug],
    queryFn: () => getDepartment(slug),
    enabled: Boolean(slug),
    retry: false,
  });

  const trimmed = within.trim();
  const searchQuery = useQuery({
    queryKey: ["registry-dept-search", slug, trimmed],
    queryFn: () => searchRegistry({ q: trimmed, department: slug }),
    enabled: trimmed.length > 0,
    retry: false,
  });

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const next = new URLSearchParams();
    if (search.trim()) next.set("q", search.trim());
    setParams(next);
  };

  const profile = deptQuery.data?.profile;
  const cards = trimmed
    ? (searchQuery.data?.datasets.items ?? [])
    : (deptQuery.data?.datasets ?? []);
  // Loaders on every fetch so stale content never flashes as current.
  // NOTE: the within-department search is disabled until a term is typed;
  // a disabled query is perpetually "pending", so only treat it as loading
  // while an actual search term is active.
  const deptLoading = deptQuery.isPending || deptQuery.isFetching;
  const deptSearching = trimmed.length > 0 && (searchQuery.isPending || searchQuery.isFetching);

  return (
    <div className="page-container mx-auto w-full max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      <nav aria-label={t("breadcrumb")} className="mb-4 text-sm" style={{ color: "var(--text-muted)" }}>
        <Link to="/" style={{ color: "var(--blue-700)" }}>{t("navHome")}</Link>
        {" / "}
        <Link to="/departments" style={{ color: "var(--blue-700)" }}>{t("navDepartments")}</Link>
        {" / "}
        <span style={{ color: "var(--text)" }}>{humanizeRaw(profile?.display_name ?? slug)}</span>
      </nav>

      {deptLoading && <LoadingBlock lines={4} />}
      {!deptLoading && deptQuery.error && (
        <ErrorBlock message={t("deptLoadError")} onRetry={() => deptQuery.refetch()} />
      )}
      {!deptLoading && deptQuery.data && profile && (
        <div>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-[minmax(0,1fr)_280px] md:items-start">
            <div>
              <h1 className="font-bold" style={{ color: "var(--navy-900)", fontSize: "1.75rem" }}>
                {profile.display_name ? humanizeRaw(profile.display_name) : humanizeRaw(slug)}
              </h1>
              {profile.description ? (
                <p className="mt-1 max-w-3xl text-sm" style={{ color: "var(--text)", fontSize: "0.9375rem" }}>
                  {profile.description}
                </p>
              ) : (
                <p className="not-provided mt-1 text-sm">{t("noDescription")}</p>
              )}
              <p className="mt-2 text-sm" style={{ color: "var(--text)", fontSize: "0.9375rem" }} role="status">
                {t(profile.dataset_count === 1 ? "datasetCountOne" : "datasetCountOther", { count: profile.dataset_count })}
                {" · "}
                {t(profile.table_count === 1 ? "tableCountOne" : "tableCountOther", { count: profile.table_count })}
              </p>
            </div>
            <StewardCard name={profile.steward} />
          </div>

          <form onSubmit={onSubmit} role="search" aria-label={t("searchWithinDept")} className="mt-6 flex w-full flex-col gap-2 sm:flex-row">
            <label htmlFor="dept-search" className="sr-only">
              {t("searchWithin", { name: profile.display_name ?? "" })}
            </label>
            <input
              id="dept-search"
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={`${t("searchWithin", { name: profile.display_name ?? "" })}…`}
              className="min-w-64 flex-1"
              style={{
                border: "1px solid var(--border)",
                borderRadius: 6,
                padding: "0.625rem 0.75rem",
                fontSize: "1rem",
                color: "var(--text)",
                background: "var(--bg)",
                width: "100%",
              }}
            />
            <button type="submit" className="btn-primary" style={{ fontSize: "0.9375rem" }}>
              {t("search")}
            </button>
            {trimmed && (
              <button
                type="button"
                onClick={() => { setSearch(""); setParams(new URLSearchParams()); }}
                className="btn-secondary"
                style={{ fontSize: "0.9375rem" }}
              >
                {t("clear")}
              </button>
            )}
          </form>

          <div className="mt-6">
            {deptSearching && <LoadingBlock lines={3} />}
            {!deptSearching && searchQuery.error && (
              <ErrorBlock message={t("searchUnavailable")} onRetry={() => searchQuery.refetch()} />
            )}
            {!deptSearching && !searchQuery.error && cards.length === 0 && (
              <EmptyBlock
                title={trimmed ? t("noResultsInDept", { q: trimmed, name: profile.display_name ?? "" }) : t("noDatasets")}
                body={
                  trimmed
                    ? t("tryBroaderCatalog")
                    : t("deptNoDatasetsHint")
                }
                action={
                  trimmed ? (
                    <Link to="/explore" className="btn-secondary" style={{ fontSize: "0.875rem" }}>
                      {t("browseFullCatalog")}
                    </Link>
                  ) : undefined
                }
              />
            )}
            {!deptSearching && cards.length > 0 && (
              <div>
                {trimmed && (
                  <p className="mb-3 text-sm" style={{ color: "var(--text-muted)" }} role="status">
                    {t(cards.length === 1 ? "resultsForOne" : "resultsForOther", { count: cards.length, q: trimmed })}
                  </p>
                )}
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  {cards.map((card) => (
                    <DatasetCard key={card.dataset} card={card} />
                  ))}
                </div>
              </div>
            )}
            {!isAuthenticated && cards.length > 0 && (
              <p className="mt-4 text-sm" style={{ color: "var(--text-muted)" }}>
                {t("someHidden")}{" "}
                {tNodes("signInToSee", {
                  link: (
                    <Link to="/login" className="font-medium" style={{ color: "var(--blue-700)" }}>
                      {t("signInLink")}
                    </Link>
                  ),
                })}
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/** Initials for the avatar: first letters of the first two words. */
function initials(name: string): string {
  return name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w.charAt(0).toUpperCase())
    .join("");
}

/**
 * The department's data steward. One steward covers every dataset in the
 * department, so it is shown here once rather than on each dataset.
 */
function StewardCard({ name }: { name: string | null | undefined }) {
  const steward = name?.trim();
  return (
    <aside
      aria-label={t("factSteward")}
      className="p-4"
      style={{ border: "1px solid var(--border)", borderRadius: 6, background: "var(--bg-alt)" }}
    >
      <p style={{ color: "var(--text-muted)", fontSize: "0.8125rem", fontWeight: 600 }}>{t("factSteward")}</p>
      {steward ? (
        <>
          <div className="mt-2 flex items-center gap-3">
            <span
              aria-hidden
              style={{
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                flexShrink: 0,
                width: 40,
                height: 40,
                borderRadius: "50%",
                background: "var(--blue-50)",
                color: "var(--blue-700)",
                fontSize: "0.875rem",
                fontWeight: 700,
              }}
            >
              {initials(steward)}
            </span>
            <span style={{ color: "var(--navy-900)", fontSize: "1rem", fontWeight: 600, overflowWrap: "anywhere" }}>
              {steward}
            </span>
          </div>
          <p className="mt-2" style={{ color: "var(--text-muted)", fontSize: "0.8125rem" }}>
            {t("stewardCovers")}
          </p>
        </>
      ) : (
        <p className="not-provided mt-2 text-sm">{t("stewardNotAssigned")}</p>
      )}
    </aside>
  );
}
