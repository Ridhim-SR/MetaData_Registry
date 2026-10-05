import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { listDatasets, listDepartments, searchRegistry } from "../api/registry";
import { AccessBadge } from "../components/registry/AccessBadge";
import { DatasetCard, RestrictedTeaser } from "../components/registry/DatasetCard";
import { EmptyBlock, ErrorBlock, Skeleton } from "../components/registry/StateBlocks";
import { useAuth } from "../contexts/AuthContext";

export function ExplorePage() {
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const department = params.get("department") ?? "";
  const visibility = params.get("visibility") ?? "";
  const [search, setSearch] = useState(q);
  const { isAuthenticated, user } = useAuth();

  useEffect(() => {
    setSearch(q);
  }, [q]);

  const trimmed = q.trim();
  const isSearch = trimmed.length > 0;

  const searchQuery = useQuery({
    queryKey: ["registry-search", trimmed, department],
    queryFn: () => searchRegistry({ q: trimmed, department: department || undefined }),
    enabled: isSearch,
    retry: false,
  });

  const catalogQuery = useQuery({
    queryKey: ["registry-catalog", department],
    queryFn: () => listDatasets({ department: department || undefined }),
    enabled: !isSearch,
    retry: false,
  });

  // Department header: reuse the cached department list (same key as
  // DepartmentGrid) so the catalogue landing shows name, description
  // and counts when ?department= is set. Search stays scoped via the
  // department param already sent by listDatasets/searchRegistry.
  const departmentsQuery = useQuery({
    queryKey: ["registry-departments"],
    queryFn: listDepartments,
    enabled: Boolean(department),
    retry: false,
    staleTime: 5 * 60 * 1000,
  });
  const activeDepartment = department
    ? (departmentsQuery.data?.items ?? []).find((d) => d.name === department) ?? null
    : null;

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const next = new URLSearchParams(params);
    if (search.trim()) next.set("q", search.trim());
    else next.delete("q");
    setParams(next);
  };

  const clearFilters = () => setParams(new URLSearchParams());

  const error: Error | null = searchQuery.error ?? catalogQuery.error;
  const isPending = isSearch ? searchQuery.isPending : catalogQuery.isPending;

  const cards = isSearch ? [] : (catalogQuery.data?.items ?? []);
  const results = isSearch ? (searchQuery.data?.data ?? []) : [];
  const teasers = isSearch ? (searchQuery.data?.teasers ?? []) : (catalogQuery.data?.teasers ?? []);
  const visibleCards =
    !isSearch && visibility === "public" ? cards.filter((c) => c.access_level === "public") : cards;

  return (
    <div className="mx-auto w-full max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      <h1 className="text-2xl font-bold text-slate-900">Catalog</h1>
      <p className="mt-1 text-sm text-slate-600">
        Search across metadata. Access levels are applied automatically
        {isAuthenticated ? " for your account" : " for public browsing"}.
      </p>

      <form onSubmit={onSubmit} role="search" className="mt-4 flex flex-col gap-2 sm:flex-row">
        <label htmlFor="catalog-search" className="sr-only">
          Search datasets, tables, keywords
        </label>
        <input
          id="catalog-search"
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search datasets, tables, keywords..."
          className="min-w-64 flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none"
        />
        <button
          type="submit"
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700"
        >
          Search
        </button>
        {(q || department || visibility) && (
          <button
            type="button"
            onClick={clearFilters}
            className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100"
          >
            Clear
          </button>
        )}
      </form>

      {department && (
        <div className="mt-4 rounded-lg border border-slate-200 bg-white p-5">
          <p className="text-xs font-medium tracking-wide text-slate-500 uppercase">Department catalogue</p>
          <h2 className="mt-1 text-xl font-bold text-slate-900">{activeDepartment?.name ?? department}</h2>
          {activeDepartment?.description && (
            <p className="mt-1 text-sm text-slate-600">{activeDepartment.description}</p>
          )}
          <p className="mt-2 text-sm text-slate-600" role="status">
            {activeDepartment
              ? `${activeDepartment.dataset_count} ${activeDepartment.dataset_count === 1 ? "dataset" : "datasets"} · ${activeDepartment.table_count} ${activeDepartment.table_count === 1 ? "table" : "tables"}`
              : "Loading catalogue info…"}
          </p>
          <p className="mt-1 text-xs text-slate-500">
            Search and browsing are scoped to this department. Datasets you cannot open appear as restricted.
          </p>
        </div>
      )}

      {visibility && !department && (
        <p className="mt-3 text-sm text-slate-600">
          Filtered by <span className="font-medium">visibility: {visibility}</span>
        </p>
      )}

      <div className="mt-6">
        {isPending && (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2" role="status" aria-label="Loading results">
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-36" />
            ))}
          </div>
        )}

        {error && (
          <ErrorBlock
            message="Unable to load catalog information. Please try again."
            onRetry={() => (isSearch ? searchQuery.refetch() : catalogQuery.refetch())}
          />
        )}

        {!isPending && !error && isSearch && results.length === 0 && teasers.length === 0 && (
          <EmptyBlock
            title={`No results for "${trimmed}".`}
            body={
              department
                ? "Try different keywords, or clear the department filter. Matches inside restricted datasets are hidden by access policy."
                : "Try different keywords, or browse departments and public data instead."
            }
          />
        )}

        {!isPending && !error && !isSearch && visibleCards.length === 0 && teasers.length === 0 && (
          <EmptyBlock
            title="No datasets match these filters."
            body={
              department && (activeDepartment?.table_count ?? 0) > 0
                ? isAuthenticated && !user?.department
                  ? "This department has published datasets, but your account has no department assigned, so they are hidden. Contact an admin to assign your department."
                  : "This department has published datasets, but none are visible to your account. Restricted datasets are hidden — request access or contact an admin."
                : "Try clearing the filters or browse public data."
            }
            action={
              <button
                onClick={clearFilters}
                className="inline-flex rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700"
              >
                Clear filters
              </button>
            }
          />
        )}

        {!isPending && !error && isSearch && (
          <div>
            <p className="mb-3 text-sm text-slate-600" role="status">
              {searchQuery.data?.total ?? 0} result{(searchQuery.data?.total ?? 0) === 1 ? "" : "s"} for “{trimmed}”
            </p>
            <ul className="grid grid-cols-1 gap-4 md:grid-cols-2">
              {results.map((t) => (
                <li
                  key={t.id}
                  className="rounded-lg border border-slate-200 bg-white p-4 transition-shadow hover:shadow-md"
                >
                  <div className="flex items-start justify-between gap-2">
                    <Link to={`/explore/${t.id}`} className="text-base font-semibold text-slate-900 hover:underline">
                      {t.name}
                    </Link>
                    <AccessBadge level={t.access_level} />
                  </div>
                  <p className="mt-1 text-xs text-slate-500">{t.fullyQualifiedName}</p>
                  <p className="mt-1 line-clamp-2 text-sm text-slate-600">{t.description || "No description"}</p>
                  <p className="mt-2 text-xs text-slate-500">{t.columns?.length ?? 0} columns</p>
                </li>
              ))}
              {teasers.map((t) => (
                <li key={t.id}>
                  <RestrictedTeaser table={t} />
                </li>
              ))}
            </ul>
          </div>
        )}

        {!isPending && !error && !isSearch && (
          <div>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {visibleCards.map((card) => (
                <DatasetCard key={card.dataset} card={card} />
              ))}
            </div>
            {teasers.length > 0 && (
              <div className="mt-8">
                <h2 className="text-lg font-semibold text-slate-900">Restricted</h2>
                <p className="mt-1 text-sm text-slate-600">These require authorization to view.</p>
                <div className="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  {teasers.map((t) => (
                    <RestrictedTeaser key={t.id} table={t} />
                  ))}
                </div>
              </div>
            )}
            {!isAuthenticated && (
              <p className="mt-4 text-sm text-slate-600">
                Some results may be hidden.{" "}
                <Link to="/login" className="font-medium underline">
                  Sign in
                </Link>{" "}
                to see metadata available to your department.
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
