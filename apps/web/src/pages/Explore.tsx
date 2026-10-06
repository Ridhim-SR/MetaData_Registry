import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, Navigate, useSearchParams } from "react-router-dom";
import { searchRegistry, type SearchScope } from "../api/registry";
import { DatasetCard } from "../components/registry/DatasetCard";
import { humanizeRaw } from "../utils/format";
import { EmptyBlock, ErrorBlock, Skeleton } from "../components/registry/StateBlocks";
import { useAuth } from "../contexts/AuthContext";

const SCOPES: Array<{ value: "" | SearchScope; label: string }> = [
  { value: "", label: "All" },
  { value: "departments", label: "Departments" },
  { value: "datasets", label: "Datasets" },
  { value: "tables", label: "Tables" },
  { value: "columns", label: "Columns" },
];

export function ExplorePage() {
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const department = params.get("department") ?? "";
  const scopeParam = params.get("scope") ?? "";
  const [search, setSearch] = useState(q);
  const [scope, setScope] = useState(scopeParam);
  const { isAuthenticated } = useAuth();

  useEffect(() => {
    setSearch(q);
  }, [q]);
  useEffect(() => {
    setScope(scopeParam);
  }, [scopeParam]);

  // Department browsing moved to /departments/:slug; keep old links working.
  const deptRedirect = department && !q.trim()
    ? `/departments/${encodeURIComponent(department)}`
    : null;

  const trimmed = q.trim();
  const isSearch = trimmed.length > 0;

  const searchQuery = useQuery({
    queryKey: ["registry-search", trimmed, scope, department],
    queryFn: () =>
      searchRegistry({
        q: trimmed,
        scope: scope || undefined,
        department: department || undefined,
      }),
    enabled: isSearch && !deptRedirect,
    retry: false,
  });

  if (deptRedirect) {
    return <Navigate to={deptRedirect} replace />;
  }

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const next = new URLSearchParams();
    if (search.trim()) next.set("q", search.trim());
    if (scope) next.set("scope", scope);
    if (department) next.set("department", department);
    setParams(next);
  };

  const onScopeChange = (value: string) => {
    setScope(value);
    const next = new URLSearchParams(params);
    if (value) next.set("scope", value);
    else next.delete("scope");
    setParams(next);
  };

  const clearFilters = () => {
    setSearch("");
    setScope("");
    setParams(new URLSearchParams());
  };

  const groups = searchQuery.data;
  const total = groups?.total ?? 0;

  return (
    <div className="mx-auto w-full max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      <h1 className="font-bold" style={{ color: "var(--navy-900)", fontSize: "1.75rem" }}>
        Catalog
      </h1>
      <p className="mt-1 text-sm" style={{ color: "var(--text-muted)", fontSize: "0.9375rem" }}>
        Search across departments, datasets, tables and columns. Access levels are
        applied automatically{isAuthenticated ? " for your account" : " for public browsing"}.
      </p>

      <form onSubmit={onSubmit} role="search" className="mt-4 flex w-full flex-col gap-2 sm:flex-row">
        <label htmlFor="catalog-search" className="sr-only">
          Search datasets, tables, keywords
        </label>
        <input
          id="catalog-search"
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search datasets, tables, keywords..."
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
        <label htmlFor="catalog-scope" className="sr-only">
          Search scope
        </label>
        <select
          id="catalog-scope"
          value={scope}
          onChange={(e) => onScopeChange(e.target.value)}
          style={{
            border: "1px solid var(--border)",
            borderRadius: 6,
            padding: "0.625rem 0.75rem",
            fontSize: "1rem",
            color: "var(--text)",
            background: "var(--bg-alt)",
          }}
        >
          {SCOPES.map((s) => (
            <option key={s.label} value={s.value}>
              {s.label}
            </option>
          ))}
        </select>
        <button type="submit" className="btn-primary" style={{ fontSize: "0.9375rem" }}>
          Search
        </button>
        {(q || scope || department) && (
          <button
            type="button"
            onClick={clearFilters}
            className="btn-secondary"
            style={{ fontSize: "0.9375rem" }}
          >
            Clear
          </button>
        )}
      </form>

      <div className="mt-6">
        {!isSearch && (
          <EmptyBlock
            title="Search the catalog."
            body="Enter keywords above, or browse by department."
            action={
              <Link to="/departments" className="btn-secondary" style={{ fontSize: "0.875rem" }}>
                Browse Departments
              </Link>
            }
          />
        )}

        {isSearch && searchQuery.isPending && (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2" role="status" aria-label="Loading results">
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-36" />
            ))}
          </div>
        )}

        {isSearch && searchQuery.error && (
          <ErrorBlock
            message="Unable to load catalog information. Please try again."
            onRetry={() => searchQuery.refetch()}
          />
        )}

        {isSearch && !searchQuery.isPending && !searchQuery.error && total === 0 && (
          <div>
            <h2 className="font-semibold" style={{ color: "var(--navy-900)", fontSize: "1.25rem" }}>
              No results for “{trimmed}”.
            </h2>
            <ul className="mt-3 list-disc space-y-2 pl-5 text-sm" style={{ color: "var(--text)", fontSize: "0.9375rem" }}>
              <li>
                Try a broader word, e.g.{" "}
                <button
                  type="button"
                  className="font-medium underline"
                  style={{ color: "var(--blue-700)" }}
                  onClick={() => {
                    const broader = trimmed.split(/\s+/)[0];
                    setSearch(broader);
                    const next = new URLSearchParams(params);
                    next.set("q", broader);
                    setParams(next);
                  }}
                >
                  “{trimmed.split(/\s+/)[0]}”
                </button>
                .
              </li>
              <li>
                <Link to="/departments" style={{ color: "var(--blue-700)" }} className="font-medium underline">
                  Browse departments
                </Link>{" "}
                to discover datasets by owner.
              </li>
              {!isAuthenticated && (
                <li>
                  <Link to="/login" style={{ color: "var(--blue-700)" }} className="font-medium underline">
                    Sign in
                  </Link>{" "}
                  to see metadata available to your department.
                </li>
              )}
            </ul>
          </div>
        )}

        {isSearch && !searchQuery.isPending && !searchQuery.error && total > 0 && groups && (
          <div>
            <p className="mb-4 text-sm" style={{ color: "var(--text-muted)" }} role="status">
              {total} result{total === 1 ? "" : "s"} for “{trimmed}”
            </p>

            {groups.departments.total > 0 && (
              <section aria-label="Departments" className="mt-6">
                <h2 className="font-semibold" style={{ color: "var(--navy-900)", fontSize: "1.125rem" }}>
                  Departments ({groups.departments.total})
                </h2>
                <ul className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  {groups.departments.items.map((d) => (
                    <li key={d.slug}>
                      <Link
                        to={`/departments/${encodeURIComponent(d.slug)}`}
                        className="block p-4"
                        style={{ border: "1px solid var(--border)", borderRadius: 6, background: "var(--bg)", textDecoration: "none" }}
                      >
                        <div className="font-semibold" style={{ color: "var(--blue-700)", fontSize: "1rem" }}>
                          {humanizeRaw(d.display_name)}
                        </div>
                        <div className="mt-1 text-sm" style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
                          {d.dataset_count} {d.dataset_count === 1 ? "dataset" : "datasets"}
                        </div>
                      </Link>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {groups.datasets.total > 0 && (
              <section aria-label="Datasets" className="mt-8">
                <h2 className="font-semibold" style={{ color: "var(--navy-900)", fontSize: "1.125rem" }}>
                  Datasets ({groups.datasets.total})
                </h2>
                <div className="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  {groups.datasets.items.map((card) => (
                    <DatasetCard key={card.dataset} card={card} />
                  ))}
                </div>
              </section>
            )}

            {groups.tables.total > 0 && (
              <section aria-label="Tables" className="mt-8">
                <h2 className="font-semibold" style={{ color: "var(--navy-900)", fontSize: "1.125rem" }}>
                  Tables ({groups.tables.total})
                </h2>
                <ul className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
                  {groups.tables.items.map((t) => (
                    <li
                      key={t.fullyQualifiedName ?? t.id}
                      className="p-4"
                      style={{ border: "1px solid var(--border)", borderRadius: 6, background: "var(--bg)" }}
                    >
                      <div className="font-semibold" style={{ color: "var(--navy-900)", fontSize: "1rem" }}>
                        {humanizeRaw(t.name)}
                      </div>
                      <p className="mt-1" style={{ color: "var(--text-muted)", fontSize: "0.8125rem" }}>
                        {humanizeRaw(t.department_display ?? t.department ?? null)}
                        {t.dataset ? ` · ${t.dataset}` : ""}
                      </p>
                      {t.description ? (
                        <p className="clamp-2 mt-1 text-sm" style={{ color: "var(--text)", fontSize: "0.9375rem" }}>
                          {t.description}
                        </p>
                      ) : (
                        <p className="not-provided mt-1 text-sm" style={{ fontSize: "0.9375rem" }}>
                          Not provided
                        </p>
                      )}
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {groups.columns.total > 0 && (
              <section aria-label="Columns" className="mt-8">
                <h2 className="font-semibold" style={{ color: "var(--navy-900)", fontSize: "1.125rem" }}>
                  Columns ({groups.columns.total})
                </h2>
                <ul className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
                  {groups.columns.items.map((c, i) => (
                    <li
                      key={`${c.dataset}-${c.table}-${c.name}-${i}`}
                      className="px-3 py-2"
                      style={{ border: "1px solid var(--border)", borderRadius: 6, background: "var(--bg)", fontSize: "0.9375rem" }}
                    >
                      <span className="font-medium" style={{ color: "var(--text)" }}>{c.name}</span>
                      <span style={{ color: "var(--text-muted)", fontSize: "0.8125rem" }}>
                        {" "}· {c.table} · {c.dataset}
                      </span>
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </div>
        )}

        {isSearch && !searchQuery.isPending && !searchQuery.error && !isAuthenticated && total > 0 && (
          <p className="mt-6 text-sm" style={{ color: "var(--text-muted)" }}>
            Some results may be hidden.{" "}
            <Link to="/login" className="font-medium" style={{ color: "var(--blue-700)" }}>
              Sign in
            </Link>{" "}
            to see metadata available to your department.
          </p>
        )}
      </div>
    </div>
  );
}
