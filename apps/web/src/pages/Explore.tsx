import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import {
  searchRegistry,
  type ColumnHit,
  type DatasetCard as Card,
  type DepartmentHit,
  type SearchResult,
  type TableHit,
} from "../api/registry";
import { AccessBadge } from "../components/registry/AccessBadge";
import { EmptyBlock, ErrorBlock, Skeleton } from "../components/registry/StateBlocks";
import { humanizeRaw } from "../utils/format";
import { useAuth } from "../contexts/AuthContext";

type Scope = "" | "departments" | "datasets" | "tables" | "columns";
type Sort = "relevance" | "updated" | "name";

/** Right preview panel ships later; this flag is the hook for it. */
const PREVIEW_PANEL_ENABLED = false;

const TYPE_OPTIONS: Array<{ value: Scope; label: string }> = [
  { value: "", label: "All" },
  { value: "departments", label: "Departments" },
  { value: "datasets", label: "Datasets" },
  { value: "tables", label: "Tables" },
  { value: "columns", label: "Columns" },
];

const SORT_OPTIONS: Array<{ value: Sort; label: string }> = [
  { value: "relevance", label: "Relevance" },
  { value: "updated", label: "Recently updated" },
  { value: "name", label: "Name A-Z" },
];

const RPP_OPTIONS = [15, 30, 50];

const ACCESS_LABELS: Record<string, string> = {
  public: "Public",
  department: "Department-only",
  restricted: "Restricted",
  confidential: "Confidential",
};

function updatedOf(item: { updated_at?: number | null }): number {
  return item.updated_at ?? -1;
}

export function ExplorePage() {
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const department = params.get("department") ?? "";
  const scopeParam = (params.get("scope") ?? "") as Scope;
  const [search, setSearch] = useState(q);
  const [scope, setScope] = useState<Scope>(scopeParam);
  const [deptSel, setDeptSel] = useState<string[]>([]);
  const [accessSel, setAccessSel] = useState<string[]>([]);
  const [tagSel, setTagSel] = useState<string[]>([]);
  const [ownerOnly, setOwnerOnly] = useState(false);
  const [sort, setSort] = useState<Sort>("relevance");
  const [rpp, setRpp] = useState(15);
  const [pages, setPages] = useState<Record<string, number>>({});
  const [deptFilterText, setDeptFilterText] = useState("");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const { isAuthenticated, user } = useAuth();

  useEffect(() => {
    setSearch(q);
  }, [q]);
  useEffect(() => {
    setScope(scopeParam);
    setPages({});
  }, [scopeParam, q]);

  // Department browsing moved to /departments/:slug; keep old links working.
  const deptRedirect = department && !q.trim()
    ? `/departments/${encodeURIComponent(department)}`
    : null;

  const trimmed = q.trim();
  const isSearch = trimmed.length > 0;

  const searchQuery = useQuery({
    queryKey: ["registry-search", trimmed, scope || "all", department],
    queryFn: () =>
      searchRegistry({
        q: trimmed,
        scope: scope || undefined,
        department: department || undefined,
      }),
    enabled: isSearch && !deptRedirect,
    retry: false,
  });

  const data: SearchResult | undefined = searchQuery.data;
  // Loader on every fetch so previous results never flash as current.
  const searching = searchQuery.isPending || searchQuery.isFetching;

  const toggleList = (list: string[], v: string, set: (next: string[]) => void) =>
    set(list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const next = new URLSearchParams();
    if (search.trim()) next.set("q", search.trim());
    if (scope) next.set("scope", scope);
    if (department) next.set("department", department);
    setDeptSel([]);
    setAccessSel([]);
    setTagSel([]);
    setOwnerOnly(false);
    setPages({});
    setParams(next);
  };

  const onScopeChange = (value: Scope) => {
    setScope(value);
    setPages({});
    const next = new URLSearchParams(params);
    if (value) next.set("scope", value);
    else next.delete("scope");
    setParams(next);
  };

  const clearFilters = () => {
    setSearch("");
    setScope("");
    setDeptSel([]);
    setAccessSel([]);
    setTagSel([]);
    setOwnerOnly(false);
    setPages({});
    setParams(new URLSearchParams());
  };

  const clearAllFilters = () => {
    setDeptSel([]);
    setAccessSel([]);
    setTagSel([]);
    setOwnerOnly(false);
    setPages({});
  };

  const hasFilters =
    deptSel.length > 0 || accessSel.length > 0 || tagSel.length > 0 || ownerOnly;

  // ---- client-side filtering (visibility already decided by the backend) ----
  const cardsByDataset = useMemo(() => {
    const map = new Map<string, Card>();
    for (const c of data?.datasets.items ?? []) map.set(c.dataset, c);
    return map;
  }, [data]);

  const deptOptions = useMemo(() => {
    const map = new Map<string, { slug: string; display: string; count: number }>();
    for (const d of data?.departments.items ?? []) {
      map.set(d.slug, {
        slug: d.slug,
        display: d.display_name || d.slug,
        count: d.dataset_count ?? 0,
      });
    }
    for (const c of data?.datasets.items ?? []) {
      const slug = c.service;
      const cur = map.get(slug);
      if (cur) cur.count += 1;
      else map.set(slug, { slug, display: c.department_display ?? c.department ?? slug, count: 1 });
    }
    return [...map.values()].sort((a, b) => a.display.localeCompare(b.display));
  }, [data]);

  const tagOptions = useMemo(() => {
    const map = new Map<string, number>();
    for (const c of data?.datasets.items ?? []) {
      for (const t of c.tags ?? []) map.set(t, (map.get(t) ?? 0) + 1);
    }
    for (const t of data?.tables.items ?? []) {
      for (const tag of t.tags ?? []) map.set(tag, (map.get(tag) ?? 0) + 1);
    }
    return [...map.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [data]);

  const accessOptions = useMemo(() => {
    const set = new Set<string>();
    for (const c of data?.datasets.items ?? []) set.add(c.access_level);
    return [...set].sort();
  }, [data]);

  const passDept = (slug: string) => deptSel.length === 0 || deptSel.includes(slug);
  const passAccess = (level: string) => accessSel.length === 0 || accessSel.includes(level);
  const passOwner = (ownerDept: string | null | undefined) =>
    !ownerOnly || (isAuthenticated && !!user?.department && ownerDept === user.department);

  const filteredDatasets = useMemo(() => {
    let items = (data?.datasets.items ?? []).filter(
      (c) =>
        passDept(c.service) &&
        passAccess(c.access_level) &&
        passOwner(c.department) &&
        (tagSel.length === 0 || (c.tags ?? []).some((t) => tagSel.includes(t))),
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
    if (sort === "name") items = [...items].sort((a, b) => (a.name || "").localeCompare(b.name || ""));
    else if (sort === "updated")
      items = [...items].sort((a, b) => updatedOf(b) - updatedOf(a));
    return items;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, deptSel, accessSel, tagSel, ownerOnly, sort, user?.department, isAuthenticated]);

  const filteredTables = useMemo(() => {
    const parentOk = (t: TableHit) => {
      const parent = t.dataset ? cardsByDataset.get(t.dataset) : undefined;
      const service = t.dataset ? t.dataset.split(".")[0] : "";
      if (!passDept(service)) return false;
      if (parent && !passAccess(parent.access_level)) return false;
      if (parent && !passOwner(parent.department)) return false;
      if (tagSel.length > 0 && !(t.tags ?? []).some((tag) => tagSel.includes(tag))) return false;
      return true;
    };
    let items = (data?.tables.items ?? []).filter(parentOk);
    if (sort === "name") items = [...items].sort((a, b) => (a.name || "").localeCompare(b.name || ""));
    else if (sort === "updated") items = [...items].sort((a, b) => updatedOf(b) - updatedOf(a));
    return items;
  }, [data, cardsByDataset, deptSel, accessSel, tagSel, ownerOnly, sort,
    user?.department, isAuthenticated]);

  const filteredColumns = useMemo(() => {
    const parentOk = (c: ColumnHit) => {
      const parent = c.dataset ? cardsByDataset.get(c.dataset) : undefined;
      const service = c.dataset ? c.dataset.split(".")[0] : "";
      if (!passDept(service)) return false;
      if (parent && !passAccess(parent.access_level)) return false;
      if (parent && !passOwner(parent.department)) return false;
      return true;
    };
    let items = (data?.columns.items ?? []).filter(parentOk);
    if (sort === "name") items = [...items].sort((a, b) => (a.name || "").localeCompare(b.name || ""));
    return items;
  }, [data, cardsByDataset, deptSel, accessSel, ownerOnly, sort, isAuthenticated]);

  const filteredDepartments = useMemo(() => {
    let items: DepartmentHit[] = (data?.departments.items ?? []).filter((d) =>
      deptSel.length === 0 ? true : deptSel.includes(d.slug),
    );
    if (sort === "name")
      items = [...items].sort((a, b) => (a.display_name || "").localeCompare(b.display_name || ""));
    return items;
  }, [data, deptSel, sort]);

  const activeGroups: Scope[] =
    scope === "" ? ["departments", "datasets", "tables", "columns"] : [scope];

  const groupTotals: Record<Exclude<Scope, "">, number> = {
    departments: filteredDepartments.length,
    datasets: filteredDatasets.length,
    tables: filteredTables.length,
    columns: filteredColumns.length,
  };

  const serverTotals = {
    departments: data?.departments.total ?? 0,
    datasets: data?.datasets.total ?? 0,
    tables: data?.tables.total ?? 0,
    columns: data?.columns.total ?? 0,
  };

  const filteredTotal =
    groupTotals.departments + groupTotals.datasets + groupTotals.tables + groupTotals.columns;

  const pageFor = (g: string) => pages[g] ?? 1;
  const pageCount = (total: number) => Math.max(1, Math.ceil(total / rpp));
  const paged = <T,>(items: T[], g: string): T[] => {
    const p = Math.min(pageFor(g), pageCount(items.length));
    return items.slice((p - 1) * rpp, p * rpp);
  };

  if (deptRedirect) {
    return <Navigate to={deptRedirect} replace />;
  }

  const panel = (
    <div>
      <h2 className="font-semibold" style={{ color: "var(--navy-900)", fontSize: "1rem" }}>
        Result types
      </h2>
      <ul className="mt-2 space-y-1">
        {TYPE_OPTIONS.map((o) => {
          const count =
            o.value === "" ? (data?.total ?? 0) : serverTotals[o.value as Exclude<Scope, "">];
          const active = scope === o.value;
          return (
            <li key={o.label}>
              <button
                type="button"
                onClick={() => onScopeChange(o.value)}
                aria-pressed={active}
                className="flex w-full items-center justify-between rounded-md px-3 py-1.5"
                style={{
                  fontSize: "0.875rem",
                  background: active ? "var(--blue-50)" : "transparent",
                  color: active ? "var(--navy-900)" : "var(--text)",
                  fontWeight: active ? 600 : 400,
                  border: "none",
                  cursor: "pointer",
                  textAlign: "left",
                }}
              >
                <span>{o.label}</span>
                <span style={{ color: "var(--text-muted)" }}>{isSearch ? count : "–"}</span>
              </button>
            </li>
          );
        })}
      </ul>

      <div className="mt-6 flex items-center justify-between">
        <h2 className="font-semibold" style={{ color: "var(--navy-900)", fontSize: "1rem" }}>
          Filters
        </h2>
        {hasFilters && (
          <button
            type="button"
            onClick={clearAllFilters}
            className="underline"
            style={{ color: "var(--blue-700)", fontSize: "0.875rem", background: "none", border: "none", cursor: "pointer" }}
          >
            Clear all
          </button>
        )}
      </div>

      <h3 className="mt-4 font-medium" style={{ color: "var(--text)", fontSize: "0.875rem" }}>
        Department
      </h3>
      {deptOptions.length > 4 && (
        <input
          type="search"
          value={deptFilterText}
          onChange={(e) => setDeptFilterText(e.target.value)}
          placeholder="Find department…"
          aria-label="Find department"
          className="mt-2 w-full"
          style={{ border: "1px solid var(--border)", borderRadius: 6, padding: "0.35rem 0.6rem", fontSize: "0.875rem" }}
        />
      )}
      <ul className="mt-2 max-h-56 space-y-1 overflow-y-auto">
        {deptOptions
          .filter((d) => d.display.toLowerCase().includes(deptFilterText.trim().toLowerCase()))
          .map((d) => (
            <li key={d.slug}>
              <label className="flex cursor-pointer items-center gap-2" style={{ fontSize: "0.875rem", color: "var(--text)" }}>
                <input
                  type="checkbox"
                  checked={deptSel.includes(d.slug)}
                  onChange={() => toggleList(deptSel, d.slug, setDeptSel)}
                />
                <span className="flex-1">{humanizeRaw(d.display)}</span>
                <span style={{ color: "var(--text-muted)" }}>{d.count}</span>
              </label>
            </li>
          ))}
        {deptOptions.length === 0 && (
          <li style={{ fontSize: "0.875rem", color: "var(--text-muted)" }}>No departments in these results.</li>
        )}
      </ul>

      <h3 className="mt-4 font-medium" style={{ color: "var(--text)", fontSize: "0.875rem" }}>
        Access level
      </h3>
      <ul className="mt-2 space-y-1">
        {accessOptions.length === 0 && (
          <li style={{ fontSize: "0.875rem", color: "var(--text-muted)" }}>No levels in these results.</li>
        )}
        {accessOptions.map((level) => (
          <li key={level}>
            <label className="flex cursor-pointer items-center gap-2" style={{ fontSize: "0.875rem", color: "var(--text)" }}>
              <input
                type="checkbox"
                checked={accessSel.includes(level)}
                onChange={() => toggleList(accessSel, level, setAccessSel)}
              />
              <span>{ACCESS_LABELS[level] ?? level}</span>
            </label>
          </li>
        ))}
      </ul>

      <h3 className="mt-4 font-medium" style={{ color: "var(--text)", fontSize: "0.875rem" }}>
        Tags
      </h3>
      <ul className="mt-2 max-h-48 space-y-1 overflow-y-auto">
        {tagOptions.length === 0 && (
          <li style={{ fontSize: "0.875rem", color: "var(--text-muted)" }}>No tags in these results.</li>
        )}
        {tagOptions.map(([tag, count]) => (
          <li key={tag}>
            <label className="flex cursor-pointer items-center gap-2" style={{ fontSize: "0.875rem", color: "var(--text)" }}>
              <input
                type="checkbox"
                checked={tagSel.includes(tag)}
                onChange={() => toggleList(tagSel, tag, setTagSel)}
              />
              <span className="flex-1" style={{ overflowWrap: "anywhere" }}>{tag}</span>
              <span style={{ color: "var(--text-muted)" }}>{count}</span>
            </label>
          </li>
        ))}
      </ul>

      {isAuthenticated && (
        <>
          <h3 className="mt-4 font-medium" style={{ color: "var(--text)", fontSize: "0.875rem" }}>
            Owner
          </h3>
          <label className="mt-2 flex cursor-pointer items-center gap-2" style={{ fontSize: "0.875rem", color: "var(--text)" }}>
            <input type="checkbox" checked={ownerOnly} onChange={(e) => setOwnerOnly(e.target.checked)} />
            <span>My department only</span>
          </label>
        </>
      )}
    </div>
  );

  return (
    <div className="mx-auto w-full px-4 py-8 sm:px-6 lg:px-8" style={{ maxWidth: 1400 }}>
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
        <button type="submit" className="btn-primary" style={{ fontSize: "0.9375rem" }}>
          Search
        </button>
        {(q || scope || department) && (
          <button type="button" onClick={clearFilters} className="btn-secondary" style={{ fontSize: "0.9375rem" }}>
            Clear
          </button>
        )}
      </form>

      <button
        type="button"
        onClick={() => setDrawerOpen(true)}
        className="btn-secondary mt-4 lg:hidden"
        style={{ fontSize: "0.9375rem" }}
        aria-haspopup="dialog"
      >
        Filters{hasFilters ? " •" : ""}
      </button>

      <div className="mt-6 flex items-start gap-6">
        <aside
          aria-label="Search filters"
          className="hidden w-64 shrink-0 lg:block"
          style={{ width: 260 }}
        >
          {panel}
        </aside>

        {drawerOpen && (
          <div role="dialog" aria-modal="true" aria-label="Filters" className="lg:hidden"
            style={{ position: "fixed", inset: 0, zIndex: 60 }}>
            <div
              aria-hidden
              onClick={() => setDrawerOpen(false)}
              style={{ position: "absolute", inset: 0, background: "rgba(0,0,0,0.4)" }}
            />
            <div style={{
              position: "absolute", top: 0, bottom: 0, left: 0, width: "85%", maxWidth: 340,
              background: "var(--bg)", borderRight: "1px solid var(--border)",
              padding: "1rem", overflowY: "auto",
            }}>
              <div className="mb-3 flex items-center justify-between">
                <span className="font-semibold" style={{ color: "var(--navy-900)", fontSize: "1rem" }}>Filters</span>
                <button
                  type="button"
                  onClick={() => setDrawerOpen(false)}
                  className="btn-secondary"
                  style={{ padding: "0.25rem 0.75rem", fontSize: "0.875rem" }}
                >
                  Close
                </button>
              </div>
              {panel}
            </div>
          </div>
        )}

        <div className="min-w-0 flex-1">
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

          {isSearch && searching && (
            <div className="grid grid-cols-1 gap-4" role="status" aria-label="Loading results">
              {[0, 1, 2].map((i) => (
                <Skeleton key={i} className="h-28" />
              ))}
            </div>
          )}

          {isSearch && !searching && searchQuery.error && (
            <ErrorBlock
              message="Unable to load catalog information. Please try again."
              onRetry={() => searchQuery.refetch()}
            />
          )}

          {isSearch && !searching && !searchQuery.error && (data?.total ?? 0) === 0 && (
            <div>
              <h2 className="font-semibold" style={{ color: "var(--navy-900)", fontSize: "1.25rem" }}>
                No results for “{trimmed}”.
              </h2>
              <ul className="mt-3 list-disc space-y-2 pl-5" style={{ color: "var(--text)", fontSize: "0.9375rem" }}>
                <li>
                  Try a broader word, e.g.{" "}
                  <button
                    type="button"
                    className="font-medium underline"
                    style={{ color: "var(--blue-700)", background: "none", border: "none", cursor: "pointer", padding: 0, fontSize: "inherit" }}
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

          {isSearch && !searching && !searchQuery.error && (data?.total ?? 0) > 0 && (
            <div>
              <div className="flex flex-wrap items-center gap-3">
                <h2 className="font-semibold" style={{ color: "var(--navy-900)", fontSize: "1.25rem" }} role="status">
                  {filteredTotal} result{filteredTotal === 1 ? "" : "s"} for “{trimmed}”
                </h2>
                <div className="ml-auto flex flex-wrap items-center gap-2">
                  <label htmlFor="sort" className="sr-only">Sort results</label>
                  <select
                    id="sort"
                    value={sort}
                    onChange={(e) => setSort(e.target.value as Sort)}
                    style={{ border: "1px solid var(--border)", borderRadius: 6, padding: "0.35rem 0.6rem", fontSize: "0.875rem", background: "var(--bg)" }}
                  >
                    {SORT_OPTIONS.map((o) => (
                      <option key={o.value} value={o.value}>{o.label}</option>
                    ))}
                  </select>
                  <label htmlFor="rpp" className="sr-only">Records per page</label>
                  <select
                    id="rpp"
                    value={rpp}
                    onChange={(e) => { setRpp(Number(e.target.value)); setPages({}); }}
                    style={{ border: "1px solid var(--border)", borderRadius: 6, padding: "0.35rem 0.6rem", fontSize: "0.875rem", background: "var(--bg)" }}
                  >
                    {RPP_OPTIONS.map((n) => (
                      <option key={n} value={n}>{n} / page</option>
                    ))}
                  </select>
                </div>
              </div>

              {activeGroups.includes("departments") && groupTotals.departments > 0 && (
                <GroupSection
                  title="Departments"
                  count={groupTotals.departments}
                  page={pageFor("departments")}
                  pages={pageCount(groupTotals.departments)}
                  onPage={(p) => setPages((prev) => ({ ...prev, departments: p }))}
                >
                  <ul className="space-y-0">
                    {paged(filteredDepartments, "departments").map((d) => (
                      <li
                        key={d.slug}
                        className="py-3"
                        style={{ borderBottom: "1px solid var(--border)" }}
                      >
                        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>Department</p>
                        <Link
                          to={`/departments/${encodeURIComponent(d.slug)}`}
                          style={{ color: "var(--blue-700)", fontSize: "1.0625rem", fontWeight: 600 }}
                        >
                          {humanizeRaw(d.display_name)}
                        </Link>
                        <p className="mt-0.5" style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
                          {d.dataset_count} {d.dataset_count === 1 ? "dataset" : "datasets"}
                        </p>
                      </li>
                    ))}
                  </ul>
                </GroupSection>
              )}

              {activeGroups.includes("datasets") && groupTotals.datasets > 0 && (
                <GroupSection
                  title="Datasets"
                  count={groupTotals.datasets}
                  page={pageFor("datasets")}
                  pages={pageCount(groupTotals.datasets)}
                  onPage={(p) => setPages((prev) => ({ ...prev, datasets: p }))}
                >
                  <ul className="space-y-0">
                    {paged(filteredDatasets, "datasets").map((c) => (
                      <DatasetRow key={c.dataset} card={c} />
                    ))}
                  </ul>
                </GroupSection>
              )}

              {activeGroups.includes("tables") && groupTotals.tables > 0 && (
                <GroupSection
                  title="Tables"
                  count={groupTotals.tables}
                  page={pageFor("tables")}
                  pages={pageCount(groupTotals.tables)}
                  onPage={(p) => setPages((prev) => ({ ...prev, tables: p }))}
                >
                  <ul className="space-y-0">
                    {paged(filteredTables, "tables").map((t) => (
                      <ClickableLi
                        key={t.fullyQualifiedName ?? t.id}
                        url={tableUrl(t.dataset, t.name)}
                        className="py-3"
                        itemStyle={{ borderBottom: "1px solid var(--border)" }}
                      >
                        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
                          {humanizeRaw(t.department_display ?? t.department ?? null)}
                          {t.dataset ? ` > ${humanizeRaw(datasetName(t.dataset, cardsByDataset))}` : ""}
                        </p>
                        <div className="mt-0.5 flex flex-wrap items-center gap-2">
                          <span className="font-semibold" style={{ color: "var(--navy-900)", fontSize: "1.0625rem" }}>
                            {humanizeRaw(t.name)}
                          </span>
                        </div>
                        {t.description ? (
                          <p className="clamp-2 mt-1" style={{ color: "var(--text)", fontSize: "0.9375rem" }}>
                            {t.description}
                          </p>
                        ) : (
                          <p className="not-provided mt-1" style={{ fontSize: "0.9375rem" }}>No description</p>
                        )}
                        {(t.matched_in?.length || t.matched_columns?.length) ? (
                          <p className="mt-1" style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
                            Matched in: {(t.matched_in ?? []).join(", ")}
                            {(t.matched_columns ?? []).length > 0 &&
                              ` (${(t.matched_columns ?? []).join(", ")})`}
                          </p>
                        ) : null}
                      </ClickableLi>
                    ))}
                  </ul>
                </GroupSection>
              )}

              {activeGroups.includes("columns") && groupTotals.columns > 0 && (
                <GroupSection
                  title="Columns"
                  count={groupTotals.columns}
                  page={pageFor("columns")}
                  pages={pageCount(groupTotals.columns)}
                  onPage={(p) => setPages((prev) => ({ ...prev, columns: p }))}
                >
                  <ul className="space-y-0">
                    {paged(filteredColumns, "columns").map((c, i) => (
                      <ClickableLi
                        key={`${c.dataset}-${c.table}-${c.name}-${i}`}
                        url={tableUrl(c.dataset, c.table, c.name)}
                        className="py-2"
                        itemStyle={{ borderBottom: "1px solid var(--border)", fontSize: "0.9375rem" }}
                      >
                        <span className="font-medium" style={{ color: "var(--text)" }}>{c.name}</span>
                        <span style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
                          {" "}· {humanizeRaw(c.table)} · {c.dataset ? humanizeRaw(datasetName(c.dataset, cardsByDataset)) : ""}
                        </span>
                      </ClickableLi>
                    ))}
                  </ul>
                </GroupSection>
              )}

              {filteredTotal === 0 && (
                <div className="mt-4">
                  <h3 className="font-semibold" style={{ color: "var(--navy-900)", fontSize: "1.125rem" }}>
                    No results match these filters.
                  </h3>
                  <p className="mt-1" style={{ color: "var(--text-muted)", fontSize: "0.9375rem" }}>
                    Try removing a filter, or{" "}
                    <button
                      type="button"
                      onClick={clearAllFilters}
                      className="underline"
                      style={{ color: "var(--blue-700)", background: "none", border: "none", cursor: "pointer", padding: 0, fontSize: "inherit" }}
                    >
                      clear all filters
                    </button>
                    .
                  </p>
                </div>
              )}

              {!isAuthenticated && (
                <p className="mt-6" style={{ color: "var(--text-muted)", fontSize: "0.9375rem" }}>
                  Some results may be hidden.{" "}
                  <Link to="/login" className="font-medium" style={{ color: "var(--blue-700)" }}>
                    Sign in
                  </Link>{" "}
                  to see metadata available to your department.
                </p>
              )}
            </div>
          )}
        </div>

        {PREVIEW_PANEL_ENABLED && (
          <aside aria-label="Preview" style={{ width: 320 }}>
            {/* Right preview panel hook: render dataset preview here when enabled. */}
          </aside>
        )}
      </div>
    </div>
  );
}

function datasetName(fqn: string, cards: Map<string, Card>): string {
  return cards.get(fqn)?.name ?? fqn.split(".").slice(-1)[0];
}

function tableUrl(dataset: string | undefined, table: string | undefined, column?: string): string | null {
  if (!dataset || !table) return null;
  const base = `/datasets/${encodeURIComponent(dataset)}/tables/${encodeURIComponent(table)}`;
  return column ? `${base}?column=${encodeURIComponent(column)}` : base;
}

function ClickableLi({
  url, children, className, itemStyle,
}: {
  url: string | null;
  children: React.ReactNode;
  className?: string;
  itemStyle?: React.CSSProperties;
}) {
  const navigate = useNavigate();
  if (!url) {
    return (
      <li className={className} style={itemStyle}>
        {children}
      </li>
    );
  }
  return (
    <li
      role="link"
      tabIndex={0}
      aria-label="Open table details"
      className={className}
      style={{ ...itemStyle, cursor: "pointer" }}
      onClick={() => navigate(url)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          navigate(url);
        }
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.background = "var(--bg-alt)";
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.background = "";
      }}
    >
      {children}
    </li>
  );
}

function GroupSection({
  title, count, page, pages, onPage, children,
}: {
  title: string;
  count: number;
  page: number;
  pages: number;
  onPage: (p: number) => void;
  children: React.ReactNode;
}) {
  const safePage = Math.min(page, pages);
  return (
    <section aria-label={title} className="mt-8">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="font-semibold" style={{ color: "var(--navy-900)", fontSize: "1.125rem" }}>
          {title} ({count})
        </h2>
        {pages > 1 && (
          <div className="ml-auto flex items-center gap-2" style={{ fontSize: "0.875rem", color: "var(--text-muted)" }}>
            <button
              type="button"
              disabled={safePage <= 1}
              onClick={() => onPage(safePage - 1)}
              className="btn-secondary"
              style={{ padding: "0.2rem 0.7rem", fontSize: "0.875rem" }}
            >
              ‹ Prev
            </button>
            <span>Page {safePage} of {pages}</span>
            <button
              type="button"
              disabled={safePage >= pages}
              onClick={() => onPage(safePage + 1)}
              className="btn-secondary"
              style={{ padding: "0.2rem 0.7rem", fontSize: "0.875rem" }}
            >
              Next ›
            </button>
          </div>
        )}
      </div>
      <div className="mt-2">{children}</div>
    </section>
  );
}

function DatasetRow({ card }: { card: Card }) {
  const dept = card.department_display ?? card.department ?? "Not provided";
  const description =
    (card.tables ?? []).map((t) => t.description?.trim()).find(Boolean) ??
    card.description?.trim() ??
    "";
  return (
    <li className="py-3" style={{ borderBottom: "1px solid var(--border)" }}>
      <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
        {humanizeRaw(dept === "Not provided" ? null : dept)} &gt; {humanizeRaw(card.name)}
      </p>
      <div className="mt-0.5 flex flex-wrap items-center gap-2">
        <Link
          to={`/datasets/${encodeURIComponent(card.dataset)}`}
          style={{ color: "var(--blue-700)", fontSize: "1.0625rem", fontWeight: 600 }}
        >
          {humanizeRaw(card.name)}
        </Link>
        <AccessBadge level={card.access_level} />
      </div>
      {description ? (
        <p className="clamp-2 mt-1" style={{ color: "var(--text)", fontSize: "0.9375rem" }}>
          {description}
        </p>
      ) : (
        <p className="not-provided mt-1" style={{ fontSize: "0.9375rem" }}>No description</p>
      )}
      <p className="mt-1" style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
        {card.table_count} {card.table_count === 1 ? "table" : "tables"}
      </p>
    </li>
  );
}
