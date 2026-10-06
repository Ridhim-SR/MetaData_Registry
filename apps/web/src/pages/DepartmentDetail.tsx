import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { getDepartment, searchRegistry } from "../api/registry";
import { humanizeRaw } from "../utils/format";
import { DatasetCard } from "../components/registry/DatasetCard";
import { EmptyBlock, ErrorBlock, LoadingBlock } from "../components/registry/StateBlocks";
import { useAuth } from "../contexts/AuthContext";

export function DepartmentDetailPage() {
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

  return (
    <div className="mx-auto w-full max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      <nav aria-label="Breadcrumb" className="mb-4 text-sm" style={{ color: "var(--text-muted)" }}>
        <Link to="/" style={{ color: "var(--blue-700)" }}>Home</Link>
        {" / "}
        <Link to="/departments" style={{ color: "var(--blue-700)" }}>Departments</Link>
        {" / "}
        <span style={{ color: "var(--text)" }}>{humanizeRaw(profile?.display_name ?? slug)}</span>
      </nav>

      {deptQuery.isPending && <LoadingBlock lines={4} />}
      {deptQuery.error && (
        <ErrorBlock message="Unable to load this department. Please try again." onRetry={() => deptQuery.refetch()} />
      )}
      {deptQuery.data && profile && (
        <div>
          <h1 className="font-bold" style={{ color: "var(--navy-900)", fontSize: "1.75rem" }}>
            {profile.display_name ? humanizeRaw(profile.display_name) : humanizeRaw(slug)}
          </h1>
          {profile.description ? (
            <p className="mt-1 max-w-3xl text-sm" style={{ color: "var(--text)", fontSize: "0.9375rem" }}>
              {profile.description}
            </p>
          ) : (
            <p className="not-provided mt-1 text-sm">Not provided</p>
          )}
          <p className="mt-2 text-sm" style={{ color: "var(--text)", fontSize: "0.9375rem" }} role="status">
            {profile.dataset_count} {profile.dataset_count === 1 ? "dataset" : "datasets"}
            {" · "}
            {profile.table_count} {profile.table_count === 1 ? "table" : "tables"}
          </p>

          <form onSubmit={onSubmit} role="search" aria-label="Search within department" className="mt-6 flex w-full flex-col gap-2 sm:flex-row">
            <label htmlFor="dept-search" className="sr-only">
              Search within {profile.display_name}
            </label>
            <input
              id="dept-search"
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={`Search within ${profile.display_name}…`}
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
              Search
            </button>
            {trimmed && (
              <button
                type="button"
                onClick={() => { setSearch(""); setParams(new URLSearchParams()); }}
                className="btn-secondary"
                style={{ fontSize: "0.9375rem" }}
              >
                Clear
              </button>
            )}
          </form>

          <div className="mt-6">
            {searchQuery.isPending && <LoadingBlock lines={3} />}
            {searchQuery.error && (
              <ErrorBlock message="Search is unavailable. Please try again." onRetry={() => searchQuery.refetch()} />
            )}
            {!searchQuery.isPending && !searchQuery.error && cards.length === 0 && (
              <EmptyBlock
                title={trimmed ? `No results for "${trimmed}" in ${profile.display_name}.` : "No datasets published yet."}
                body={
                  trimmed
                    ? "Try a broader word, or browse the full catalog."
                    : "New datasets will appear here once this department publishes them."
                }
                action={
                  trimmed ? (
                    <Link to="/explore" className="btn-secondary" style={{ fontSize: "0.875rem" }}>
                      Browse full catalog
                    </Link>
                  ) : undefined
                }
              />
            )}
            {cards.length > 0 && (
              <div>
                {trimmed && (
                  <p className="mb-3 text-sm" style={{ color: "var(--text-muted)" }} role="status">
                    {cards.length} result{cards.length === 1 ? "" : "s"} for “{trimmed}”
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
                Some results may be hidden.{" "}
                <Link to="/login" className="font-medium" style={{ color: "var(--blue-700)" }}>
                  Sign in
                </Link>{" "}
                to see metadata available to your department.
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
