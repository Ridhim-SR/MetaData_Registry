import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import {
  listDatasets,
  searchRegistry,
  type ColumnHit,
  type DatasetCard as Card,
  type DepartmentHit,
  type SearchResult,
  type TableHit,
} from "../api/registry";
import { Fragment } from "react";
import { ErrorBlock, Skeleton } from "../components/registry/StateBlocks";
import { t } from "../i18n";
import { formatUpdatedAt, humanizeRaw, normalizeClassification, readableTag } from "../utils/format";
import { useAuth } from "../contexts/AuthContext";

type Scope = "" | "departments" | "datasets" | "tables" | "columns";
type Sort = "relevance" | "updated" | "name";

/** Right preview panel ships later; this flag is the hook for it. */
const PREVIEW_PANEL_ENABLED = false;

const SORT_OPTIONS: Array<{ value: Sort; label: string }> = [
  { value: "relevance", label: "Relevance" },
  { value: "updated", label: "Recently updated" },
  { value: "name", label: "Name A-Z" },
];

const RPP_OPTIONS = [15, 30, 50];

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
  const [tagSel, setTagSel] = useState<string[]>([]);
  const [sort, setSort] = useState<Sort>("relevance");
  const [rpp, setRpp] = useState(15);
  const [pages, setPages] = useState<Record<string, number>>({});
  const [deptFilterText, setDeptFilterText] = useState("");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const { isAuthenticated } = useAuth();

  useEffect(() => {
    setSearch(q);
  }, [q]);
  useEffect(() => {
    setScope(scopeParam);
    setPages({});
  }, [scopeParam, q]);
  // Keep pagination at page 1 whenever filters/sort change so results stay visible.
  useEffect(() => {
    setPages({});
  }, [deptSel, tagSel, sort]);

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

  // Browse mode (no query): list all datasets across departments once,
  // paginate + filter client-side so the frontend never renders everything.
  const browseQuery = useQuery({
    queryKey: ["registry-datasets", department],
    queryFn: () => listDatasets({ department: department || undefined }),
    enabled: !isSearch && !deptRedirect,
    retry: false,
  });

  const data: SearchResult | undefined = searchQuery.data;
  // Loader on every fetch so previous results never flash as current.
  const searching = searchQuery.isPending || searchQuery.isFetching;
  const browsing = browseQuery.isPending || browseQuery.isFetching;

  const toggleList = (list: string[], v: string, set: (next: string[]) => void) =>
    set(list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const next = new URLSearchParams();
    if (search.trim()) next.set("q", search.trim());
    if (scope) next.set("scope", scope);
    if (department) next.set("department", department);
    setDeptSel([]);
    setTagSel([]);
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

  const clearAllFilters = () => {
    setDeptSel([]);
    setTagSel([]);
    setPages({});
  };

  const hasFilters =
    deptSel.length > 0 || tagSel.length > 0;

  // ---- client-side filtering (visibility already decided by the backend) ----
  // In browse mode (no q) filters run over the full dataset list;
  // in search mode they run over the search hits.
  const baseDatasetItems = useMemo<Card[]>(
    () => (isSearch ? (data?.datasets.items ?? []) : (browseQuery.data?.items ?? [])),
    [isSearch, data, browseQuery.data],
  );

  const cardsByDataset = useMemo(() => {
    const map = new Map<string, Card>();
    for (const c of baseDatasetItems) map.set(c.dataset, c);
    return map;
  }, [baseDatasetItems]);

  const deptOptions = useMemo(() => {
    const map = new Map<string, { slug: string; display: string; count: number }>();
    for (const d of data?.departments.items ?? []) {
      if (!isSearch) continue;
      map.set(d.slug, {
        slug: d.slug,
        display: d.display_name || d.slug,
        count: d.dataset_count ?? 0,
      });
    }
    for (const c of baseDatasetItems) {
      const slug = c.service;
      const cur = map.get(slug);
      if (cur) cur.count += 1;
      else map.set(slug, { slug, display: c.department_display ?? c.department ?? slug, count: 1 });
    }
    return [...map.values()].sort((a, b) => a.display.localeCompare(b.display));
  }, [data, baseDatasetItems, isSearch]);

  const tagOptions = useMemo(() => {
    const map = new Map<string, number>();
    for (const c of baseDatasetItems) {
      for (const t of c.tags ?? []) map.set(t, (map.get(t) ?? 0) + 1);
    }
    if (isSearch) {
      for (const t of data?.tables.items ?? []) {
        for (const tag of t.tags ?? []) map.set(tag, (map.get(tag) ?? 0) + 1);
      }
    }
    return [...map.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [baseDatasetItems, data, isSearch]);

  // "MDSF.*" tags are data classification (shown without the prefix; PII is
  // shown as "Sensitive (PII)"). Everything else stays under Tags with the
  // "FieldTag."-style namespace stripped for display. Original values are
  // always kept for filtering; on a display collision the full value is
  // kept so no label appears twice in the same group.
  const classificationOptions = useMemo(
    () =>
      uniqueFilterLabels(
        tagOptions.filter(([value]) => value.startsWith("MDSF.")),
        (value) => {
          const rest = value.slice("MDSF.".length);
          return rest.toUpperCase() === "PII" ? "Sensitive (PII)" : rest;
        },
      ),
    [tagOptions],
  );
  const fieldTagOptions = useMemo(
    () =>
      uniqueFilterLabels(
        tagOptions.filter(([value]) => !value.startsWith("MDSF.")),
        (value) => readableTag({ tagFQN: value, name: value }),
      ),
    [tagOptions],
  );

  const passDept = (slug: string) => deptSel.length === 0 || deptSel.includes(slug);

  const filteredDatasets = useMemo(() => {
    let items = baseDatasetItems.filter(
      (c) =>
        passDept(c.service) &&
        (tagSel.length === 0 || (c.tags ?? []).some((t) => tagSel.includes(t))),
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
    if (sort === "name") items = [...items].sort((a, b) => (a.name || "").localeCompare(b.name || ""));
    else if (sort === "updated")
      items = [...items].sort((a, b) => updatedOf(b) - updatedOf(a));
    return items;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [baseDatasetItems, deptSel, tagSel, sort]);

  const filteredTables = useMemo(() => {
    const parentOk = (t: TableHit) => {
      const service = t.dataset ? t.dataset.split(".")[0] : "";
      if (!passDept(service)) return false;
      if (tagSel.length > 0 && !(t.tags ?? []).some((tag) => tagSel.includes(tag))) return false;
      return true;
    };
    let items = (data?.tables.items ?? []).filter(parentOk);
    if (sort === "name") items = [...items].sort((a, b) => (a.name || "").localeCompare(b.name || ""));
    else if (sort === "updated") items = [...items].sort((a, b) => updatedOf(b) - updatedOf(a));
    return items;
  }, [data, deptSel, tagSel, sort]);

  const filteredColumns = useMemo(() => {
    const parentOk = (c: ColumnHit) => {
      const service = c.dataset ? c.dataset.split(".")[0] : "";
      if (!passDept(service)) return false;
      return true;
    };
    let items = (data?.columns.items ?? []).filter(parentOk);
    if (sort === "name") items = [...items].sort((a, b) => (a.name || "").localeCompare(b.name || ""));
    return items;
  }, [data, deptSel, sort]);

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

  const filteredTotal =
    groupTotals.departments + groupTotals.datasets + groupTotals.tables + groupTotals.columns;

  const browseDeptCount = useMemo(
    () => new Set(filteredDatasets.map((c) => c.service)).size,
    [filteredDatasets],
  );
  const searchDeptCount = useMemo(() => {
    const services = new Set<string>();
    for (const c of filteredDatasets) services.add(c.service);
    for (const t of filteredTables) {
      if (t.dataset) services.add(t.dataset.split(".")[0]);
    }
    return services.size;
  }, [filteredDatasets, filteredTables]);

  const multiDept = searchDeptCount > 1;

  // Query tokens used to highlight matched terms in result titles.
  const highlightTokens = useMemo(() => {
    if (!isSearch) return [];
    return [...new Set(trimmed.toLowerCase().split(/\s+/).filter((w) => w.length >= 2))];
  }, [trimmed, isSearch]);

  const pageFor = (g: string) => pages[g] ?? 1;
  const pageCount = (total: number) => Math.max(1, Math.ceil(total / rpp));
  const paged = <T,>(items: T[], g: string): T[] => {
    const p = Math.min(pageFor(g), pageCount(items.length));
    return items.slice((p - 1) * rpp, p * rpp);
  };

  if (deptRedirect) {
    return <Navigate to={deptRedirect} replace />;
  }

  // Tabs for the search results (sidebar holds filters only now). The
  // Departments tab is hidden when its count is 0; other zero-count tabs
  // stay visible but muted.
  const visibleTabs: Array<{ value: Scope; label: string; count: number; icon: React.ReactNode }> = [
    { value: "", label: t("tabAll"), count: filteredTotal, icon: <AllIcon /> },
    ...(groupTotals.departments > 0
      ? [{ value: "departments" as Scope, label: t("tabDepartments"), count: groupTotals.departments, icon: <DeptIcon /> }]
      : []),
    { value: "datasets", label: t("tabDatasets"), count: groupTotals.datasets, icon: <DatabaseIcon /> },
    { value: "tables", label: t("tabTables"), count: groupTotals.tables, icon: <TableIcon /> },
    { value: "columns", label: t("tabColumns"), count: groupTotals.columns, icon: <ColumnsIcon /> },
  ];

  const tabRefs = useRef(new Map<string, HTMLButtonElement>());
  const handleTabKeyDown = (e: React.KeyboardEvent) => {
    const order = visibleTabs.map((tab) => tab.value);
    const idx = order.indexOf(scope);
    let next: Scope | null = null;
    if (e.key === "ArrowRight") next = order[(idx + 1) % order.length];
    else if (e.key === "ArrowLeft") next = order[(idx - 1 + order.length) % order.length];
    else if (e.key === "Home") next = order[0];
    else if (e.key === "End") next = order[order.length - 1];
    if (next !== null) {
      e.preventDefault();
      if (next !== scope) onScopeChange(next);
      requestAnimationFrame(() => tabRefs.current.get(next)?.focus());
    }
  };

  const panel = (
    <div>
      <div className="flex items-center justify-between">
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
          placeholder="Search departments…"
          aria-label="Search departments"
          className="mt-2 w-full"
          style={{ border: "1px solid var(--border)", borderRadius: 6, padding: "0.35rem 0.6rem", fontSize: "0.875rem" }}
        />
      )}
      {deptSel.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1" aria-label="Selected departments">
          {deptSel.map((slug) => {
            const opt = deptOptions.find((d) => d.slug === slug);
            return (
              <button
                key={slug}
                type="button"
                onClick={() => toggleList(deptSel, slug, setDeptSel)}
                aria-label={`Remove department filter ${opt?.display ?? slug}`}
                className="inline-flex items-center gap-1 rounded-full px-2 py-0.5"
                style={{ background: "var(--blue-50)", color: "var(--navy-900)", fontSize: "0.8125rem", border: "1px solid var(--border)", cursor: "pointer" }}
              >
                {humanizeRaw(opt?.display ?? slug)} ×
              </button>
            );
          })}
        </div>
      )}
      <ul className="mt-2 max-h-56 space-y-1 overflow-y-auto">
        {deptOptions
          .filter((d) => d.display.toLowerCase().includes(deptFilterText.trim().toLowerCase()))
          .map((d) => (
            <li key={d.slug}>
              <label className="flex cursor-pointer items-center gap-2" style={{ minHeight: "32px", fontSize: "0.9375rem", color: "var(--text)" }}>
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

      {classificationOptions.length > 0 && (
        <>
          <h3 className="mt-4 font-medium" style={{ color: "var(--text)", fontSize: "0.875rem" }}>
            {t("classificationFilter")}
          </h3>
          <FilterChecklist
            options={classificationOptions}
            selected={tagSel}
            onToggle={(value) => toggleList(tagSel, value, setTagSel)}
          />
        </>
      )}
      {fieldTagOptions.length > 0 && (
        <>
          <h3 className="mt-4 font-medium" style={{ color: "var(--text)", fontSize: "0.875rem" }}>
            Tags
          </h3>
          <FilterChecklist
            options={fieldTagOptions}
            selected={tagSel}
            onToggle={(value) => toggleList(tagSel, value, setTagSel)}
          />
        </>
      )}
    </div>
  );

  return (
    <div className="page-container mx-auto w-full px-4 py-8 pb-12 sm:px-6 lg:px-8" style={{ maxWidth: 1360 }}>
      <h1 className="font-bold" style={{ color: "var(--navy-900)", fontSize: "1.75rem" }}>
        Explore the Catalog
      </h1>
      <p className="mt-1 text-sm" style={{ color: "var(--text-muted)", fontSize: "0.9375rem" }}>
        Discover datasets, tables, columns, and metadata across government departments.
      </p>

      <form onSubmit={onSubmit} role="search" className="mt-4 flex w-full flex-col gap-2 sm:flex-row">
        <div className="relative min-w-64 flex-1">
          <label htmlFor="catalog-search" className="sr-only">
            Search datasets, tables, columns, or keywords
          </label>
          <span
            aria-hidden="true"
            style={{
              position: "absolute",
              left: "0.75rem",
              top: "50%",
              transform: "translateY(-50%)",
              display: "inline-flex",
              color: "var(--text-muted)",
              pointerEvents: "none",
            }}
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.75">
              <circle cx="7" cy="7" r="5" />
              <path d="M11 11l3.5 3.5" />
            </svg>
          </span>
          <input
            id="catalog-search"
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Escape" && search) setSearch("");
            }}
            placeholder="Search datasets, tables, columns, or keywords..."
            className="w-full"
            style={{
              border: "1px solid var(--border)",
              borderRadius: 6,
              padding: "0.625rem 0.75rem",
              paddingLeft: "2.25rem",
              paddingRight: search ? "2rem" : undefined,
              fontSize: "1rem",
              color: "var(--text)",
              background: "var(--bg)",
              width: "100%",
            }}
          />
          {search && (
            <button
              type="button"
              onClick={() => setSearch("")}
              aria-label={t("clearSearch")}
              style={{
                position: "absolute",
                right: "0.5rem",
                top: "50%",
                transform: "translateY(-50%)",
                background: "none",
                border: "none",
                cursor: "pointer",
                color: "var(--text-muted)",
                fontSize: "1rem",
                padding: "0 0.25rem",
              }}
            >
              ✕
            </button>
          )}
        </div>
        <button type="submit" className="btn-primary" style={{ fontSize: "0.9375rem" }}>
          Search
        </button>
      </form>

      <button
        type="button"
        onClick={() => setDrawerOpen(true)}
        className="btn-secondary filters-toggle mt-4"
        style={{ fontSize: "0.9375rem" }}
        aria-haspopup="dialog"
      >
        Filters{hasFilters ? " •" : ""}
      </button>

      <div className="mt-6 flex items-start gap-6" style={{ minHeight: "50vh" }}>
        <aside
          aria-label="Search filters"
          className="hidden w-64 shrink-0 lg:block"
          style={{ width: 250 }}
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
          {!isSearch && browsing && (
            <div className="grid grid-cols-1 gap-4" role="status" aria-label="Loading datasets">
              {[0, 1, 2].map((i) => (
                <Skeleton key={i} className="h-28" />
              ))}
            </div>
          )}

          {!isSearch && !browsing && browseQuery.error && (
            <ErrorBlock
              message="Unable to load catalog information. Please try again."
              onRetry={() => browseQuery.refetch()}
            />
          )}

          {!isSearch && !browsing && !browseQuery.error && (
            <div>
              <div className="flex flex-wrap items-center gap-3">
                <h2 className="font-semibold" style={{ color: "var(--navy-900)", fontSize: "1.25rem" }} role="status">
                  {filteredDatasets.length} result{filteredDatasets.length === 1 ? "" : "s"}
                  {browseDeptCount > 0 && (
                    <span className="font-normal" style={{ color: "var(--text-muted)", fontSize: "0.9375rem" }}>
                      {" "}· Across {browseDeptCount} department{browseDeptCount === 1 ? "" : "s"}
                    </span>
                  )}
                </h2>
                <div className="ml-auto flex flex-wrap items-center gap-2">
                  <label htmlFor="browse-sort" className="sr-only">Sort datasets</label>
                  <select
                    id="browse-sort"
                    value={sort}
                    onChange={(e) => setSort(e.target.value as Sort)}
                    style={{ border: "1px solid var(--border)", borderRadius: 6, padding: "0.35rem 0.6rem", fontSize: "0.875rem", background: "var(--bg)" }}
                  >
                    {SORT_OPTIONS.map((o) => (
                      <option key={o.value} value={o.value}>{o.label}</option>
                    ))}
                  </select>
                  <label htmlFor="browse-rpp" className="sr-only">Records per page</label>
                  <select
                    id="browse-rpp"
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

              {filteredDatasets.length > 0 ? (
                <GroupSection
                  title="Datasets"
                  page={pageFor("datasets")}
                  pages={pageCount(filteredDatasets.length)}
                  onPage={(p) => setPages((prev) => ({ ...prev, datasets: p }))}
                >
                  <ul style={{ display: "flex", flexDirection: "column", gap: "12px", listStyle: "none", margin: 0, padding: 0 }}>
                    {paged(filteredDatasets, "datasets").map((c) => (
                      <DatasetRow key={c.dataset} card={c} tokens={[]} />
                    ))}
                  </ul>
                </GroupSection>
              ) : (
                <div className="mt-4">
                  <h3 className="font-semibold" style={{ color: "var(--navy-900)", fontSize: "1.125rem" }}>
                    No datasets found
                  </h3>
                  <p className="mt-1" style={{ color: "var(--text-muted)", fontSize: "0.9375rem" }}>
                    Try a different search term or adjust your filters.
                  </p>
                  {(hasFilters || q) && (
                    <button
                      type="button"
                      onClick={clearAllFilters}
                      className="btn-secondary mt-3"
                      style={{ fontSize: "0.875rem" }}
                    >
                      Clear filters
                    </button>
                  )}
                </div>
              )}

              {!isAuthenticated && filteredDatasets.length > 0 && (
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
                  {searchDeptCount > 0 && (
                    <span className="font-normal" style={{ color: "var(--text-muted)", fontSize: "0.9375rem" }}>
                      {" "}· Across {searchDeptCount} department{searchDeptCount === 1 ? "" : "s"}
                    </span>
                  )}
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

              {filteredTotal > 0 && (
                <div
                  role="tablist"
                  aria-label={t("resultTypes")}
                  onKeyDown={handleTabKeyDown}
                  className="mt-4 flex gap-1"
                  style={{ overflowX: "auto", flexWrap: "nowrap", borderBottom: "1px solid var(--border)" }}
                >
                  {visibleTabs.map((tab) => {
                    const active = scope === tab.value;
                    const muted = !active && tab.count === 0;
                    return (
                      <button
                        key={tab.value || "all"}
                        ref={(el) => {
                          if (el) tabRefs.current.set(tab.value, el);
                          else tabRefs.current.delete(tab.value);
                        }}
                        type="button"
                        role="tab"
                        aria-selected={active}
                        tabIndex={active ? 0 : -1}
                        onClick={() => onScopeChange(tab.value)}
                        onMouseEnter={(e) => {
                          if (!active) e.currentTarget.style.background = "var(--bg-alt)";
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.background = "";
                        }}
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: "0.4rem",
                          background: "none",
                          border: "none",
                          borderBottom: active ? "2px solid var(--blue-700)" : "2px solid transparent",
                          padding: "0.5rem 0.75rem",
                          fontSize: "0.9375rem",
                          fontWeight: active ? 500 : 400,
                          color: active ? "var(--blue-700)" : muted ? "var(--text-muted)" : "var(--text)",
                          cursor: "pointer",
                          whiteSpace: "nowrap",
                        }}
                      >
                        <span aria-hidden="true" style={{ display: "inline-flex" }}>
                          {tab.icon}
                        </span>
                        {tab.label}{" "}
                        <span
                          style={{
                            fontSize: "0.75rem",
                            fontWeight: 600,
                            borderRadius: 999,
                            padding: "0.05rem 0.5rem",
                            background: "var(--bg-alt)",
                            border: "1px solid var(--border)",
                            color: "var(--text-muted)",
                          }}
                        >
                          {tab.count}
                        </span>
                      </button>
                    );
                  })}
                </div>
              )}

              {activeGroups.includes("departments") && groupTotals.departments > 0 && (
                <GroupSection
                  title="Departments"
                  icon={<DeptIcon />}
                  count={groupTotals.departments}
                  hideTitle={scope !== ""}
                  viewAll={scope === "" ? {
                    text: t("viewAllCount", { count: String(groupTotals.departments) }),
                    onClick: () => onScopeChange("departments"),
                    total: groupTotals.departments,
                    shown: paged(filteredDepartments, "departments").length,
                  } : undefined}
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
                  icon={<DatabaseIcon />}
                  count={groupTotals.datasets}
                  hideTitle={scope !== ""}
                  viewAll={scope === "" ? {
                    text: t("viewAllCount", { count: String(groupTotals.datasets) }),
                    onClick: () => onScopeChange("datasets"),
                    total: groupTotals.datasets,
                    shown: paged(filteredDatasets, "datasets").length,
                  } : undefined}
                  page={pageFor("datasets")}
                  pages={pageCount(groupTotals.datasets)}
                  onPage={(p) => setPages((prev) => ({ ...prev, datasets: p }))}
                >
                  <ul style={{ display: "flex", flexDirection: "column", gap: "12px", listStyle: "none", margin: 0, padding: 0 }}>
                    {paged(filteredDatasets, "datasets").map((c) => (
                      <DatasetRow key={c.dataset} card={c} tokens={highlightTokens} />
                    ))}
                  </ul>
                </GroupSection>
              )}

              {activeGroups.includes("tables") && groupTotals.tables > 0 && (
                <GroupSection
                  title="Tables"
                  icon={<TableIcon />}
                  count={groupTotals.tables}
                  hideTitle={scope !== ""}
                  viewAll={scope === "" ? {
                    text: t("viewAllCount", { count: String(groupTotals.tables) }),
                    onClick: () => onScopeChange("tables"),
                    total: groupTotals.tables,
                    shown: Math.min(5, filteredTables.length),
                  } : undefined}
                  hidePager={scope === ""}
                  page={pageFor("tables")}
                  pages={pageCount(groupTotals.tables)}
                  onPage={(p) => setPages((prev) => ({ ...prev, tables: p }))}
                >
                  <ul style={{ display: "flex", flexDirection: "column", gap: "8px", listStyle: "none", margin: 0, padding: 0 }}>
                    {(scope === "" ? filteredTables.slice(0, 5) : paged(filteredTables, "tables")).map((hit) => (
                      <TableResultCard
                        key={hit.fullyQualifiedName ?? hit.id}
                        hit={hit}
                        datasetDisplay={hit.dataset ? humanizeRaw(datasetName(hit.dataset, cardsByDataset)) : ""}
                        deptDisplay={hit.department_display ?? hit.department ?? null}
                        multiDept={multiDept}
                        tokens={highlightTokens}
                      />
                    ))}
                  </ul>
                </GroupSection>
              )}

              {activeGroups.includes("columns") && groupTotals.columns > 0 && (
                <GroupSection
                  title="Columns"
                  icon={<ColumnsIcon />}
                  count={groupTotals.columns}
                  hideTitle={scope !== ""}
                  viewAll={scope === "" ? {
                    text: t("viewAllCount", { count: String(groupTotals.columns) }),
                    onClick: () => onScopeChange("columns"),
                    total: groupTotals.columns,
                    shown: Math.min(6, filteredColumns.length),
                  } : undefined}
                  hidePager={scope === ""}
                  page={pageFor("columns")}
                  pages={pageCount(groupTotals.columns)}
                  onPage={(p) => setPages((prev) => ({ ...prev, columns: p }))}
                >
                  <ul
                    className="grid grid-cols-1 sm:grid-cols-2"
                    style={{ gap: "12px", listStyle: "none", margin: 0, padding: 0 }}
                  >
                    {(scope === "" ? filteredColumns.slice(0, 6) : paged(filteredColumns, "columns")).map((c, i) => (
                      <ColumnResultCard
                        key={`${c.dataset}-${c.table}-${c.name}-${i}`}
                        col={c}
                        datasetDisplay={c.dataset ? humanizeRaw(datasetName(c.dataset, cardsByDataset)) : ""}
                        deptDisplay={c.dataset ? cardsByDataset.get(c.dataset)?.department_display ?? null : null}
                        multiDept={multiDept}
                        tokens={highlightTokens}
                      />
                    ))}
                  </ul>
                </GroupSection>
              )}

              {filteredTotal === 0 && (
                <div className="mt-4">
                  <h3 className="font-semibold" style={{ color: "var(--navy-900)", fontSize: "1.125rem" }}>
                    No datasets found
                  </h3>
                  <p className="mt-1" style={{ color: "var(--text-muted)", fontSize: "0.9375rem" }}>
                    Try a different search term or adjust your filters.
                  </p>
                  {hasFilters && (
                    <button
                      type="button"
                      onClick={clearAllFilters}
                      className="btn-secondary mt-3"
                      style={{ fontSize: "0.875rem" }}
                    >
                      Clear filters
                    </button>
                  )}
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

function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** Wrap query-term occurrences in <mark> (accent tint); otherwise plain text. */
function Highlight({ text, tokens }: { text: string; tokens: string[] }) {
  const active = tokens.filter(Boolean);
  if (!text || active.length === 0) return <>{text}</>;
  let re: RegExp;
  try {
    re = new RegExp(`(${active.map(escapeRegExp).join("|")})`, "gi");
  } catch {
    return <>{text}</>;
  }
  const parts: Array<{ text: string; hit: boolean }> = [];
  let last = 0;
  let m: RegExpExecArray | null;
  re.lastIndex = 0;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) parts.push({ text: text.slice(last, m.index), hit: false });
    parts.push({ text: m[0], hit: true });
    last = m.index + m[0].length;
    if (m[0].length === 0) re.lastIndex += 1;
  }
  if (last < text.length) parts.push({ text: text.slice(last), hit: false });
  return (
    <>
      {parts.map((p, i) =>
        p.hit ? (
          <mark
            key={i}
            style={{ background: "var(--blue-50)", color: "inherit", borderRadius: 2, padding: "0 1px" }}
          >
            {p.text}
          </mark>
        ) : (
          <span key={i}>{p.text}</span>
        ),
      )}
    </>
  );
}

/** Cut a long breadcrumb segment from the left; full value stays in title. */
function truncateLeft(value: string, max = 26): string {
  if (value.length <= max) return value;
  return `…${value.slice(value.length - max + 1)}`;
}

function ChevronSeparator() {
  return (
    <li aria-hidden="true" style={{ display: "inline-flex", color: "var(--text-muted)" }}>
      <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M6 4l4 4-4 4" />
      </svg>
    </li>
  );
}

/** Breadcrumb path with chevron separators (never "/" or ">" text). */
function Crumbs({
  trail,
  fullPath,
}: {
  trail: Array<{ label: React.ReactNode; to?: string | null; title?: string }>;
  fullPath?: string;
}) {
  return (
    <nav aria-label="Location" title={fullPath}>
      <ol
        style={{
          display: "flex",
          flexWrap: "wrap",
          alignItems: "center",
          gap: "0.25rem",
          listStyle: "none",
          margin: 0,
          padding: 0,
        }}
      >
        {trail.map((seg, i) => (
          <Fragment key={i}>
            <li style={{ minWidth: 0 }}>
              {seg.to ? (
                <Link
                  to={seg.to}
                  title={seg.title}
                  style={{ color: "var(--blue-700)", fontSize: "0.875rem", fontWeight: 600 }}
                >
                  {seg.label}
                </Link>
              ) : (
                <span title={seg.title} style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
                  {seg.label}
                </span>
              )}
            </li>
            {i < trail.length - 1 && <ChevronSeparator />}
          </Fragment>
        ))}
      </ol>
    </nav>
  );
}

function DeptIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true" style={{ flexShrink: 0 }}>
      <path d="M2 6.5L8 2.5l6 4" />
      <path d="M3 6.5V12M6.5 6.5V12M9.5 6.5V12M13 6.5V12" />
      <path d="M2 13.5h12" />
    </svg>
  );
}

function DatabaseIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true" style={{ flexShrink: 0 }}>
      <ellipse cx="8" cy="3.5" rx="5.5" ry="2" />
      <path d="M2.5 3.5v9c0 1.1 2.5 2 5.5 2s5.5-.9 5.5-2v-9" />
      <path d="M2.5 8c0 1.1 2.5 2 5.5 2s5.5-.9 5.5-2" />
    </svg>
  );
}

function TableIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true" style={{ flexShrink: 0 }}>
      <rect x="1.5" y="2.5" width="13" height="11" rx="1.5" />
      <path d="M1.5 6h13M1.5 10h13M6 6v7" />
    </svg>
  );
}

function ColumnsIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true" style={{ flexShrink: 0 }}>
      <rect x="2" y="2" width="12" height="12" rx="2" />
      <path d="M6 2v12M10 2v12" />
    </svg>
  );
}

function AllIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true" style={{ flexShrink: 0 }}>
      <rect x="2" y="2" width="5" height="5" rx="1" />
      <rect x="9" y="2" width="5" height="5" rx="1" />
      <rect x="2" y="9" width="5" height="5" rx="1" />
      <rect x="9" y="9" width="5" height="5" rx="1" />
    </svg>
  );
}

const MONO_FONT = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace";

function tableUrl(dataset: string | undefined, table: string | undefined, column?: string): string | null {
  if (!dataset || !table) return null;
  const base = `/datasets/${encodeURIComponent(dataset)}/tables/${encodeURIComponent(table)}`;
  return column ? `${base}?column=${encodeURIComponent(column)}` : base;
}

/** Display labels for one filter group with collision disambiguation. */
function uniqueFilterLabels(
  entries: Array<[string, number]>,
  labelOf: (value: string) => string,
): Array<{ value: string; label: string; count: number }> {
  const labels = entries.map(([value]) => labelOf(value));
  const seen = new Set<string>();
  const dupes = new Set<string>();
  for (const label of labels) {
    if (seen.has(label)) dupes.add(label);
    else seen.add(label);
  }
  return entries.map(([value, count], i) => ({
    value,
    count,
    label: dupes.has(labels[i]) ? value : labels[i],
  }));
}

function FilterChecklist({
  options, selected, onToggle,
}: {
  options: Array<{ value: string; label: string; count: number }>;
  selected: string[];
  onToggle: (value: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const visible = expanded ? options : options.slice(0, 5);
  return (
    <>
      <ul className="mt-2 max-h-48 space-y-1 overflow-y-auto">
        {visible.map(({ value, label, count }) => (
          <li key={value}>
            <label className="flex cursor-pointer items-center gap-2" style={{ minHeight: "32px", fontSize: "0.9375rem", color: "var(--text)" }}>
              <input
                type="checkbox"
                checked={selected.includes(value)}
                onChange={() => onToggle(value)}
              />
              <span className="flex-1" style={{ overflowWrap: "anywhere" }}>{label}</span>
              <span style={{ color: "var(--text-muted)" }}>{count}</span>
            </label>
          </li>
        ))}
      </ul>
      {options.length > 5 && (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="mt-1 font-medium"
          style={{ color: "var(--blue-700)", background: "none", border: "none", cursor: "pointer", fontSize: "0.875rem", padding: 0 }}
        >
          {expanded ? t("showLess") : t("showMore")}
        </button>
      )}
    </>
  );
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

function Pager({
  page, pages, onPage,
}: {
  page: number;
  pages: number;
  onPage: (p: number) => void;
}) {
  const safePage = Math.min(page, pages);
  return (
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
  );
}

function GroupSection({
  title, icon, count, page, pages, onPage, children, hideTitle = false, viewAll, hidePager = false,
}: {
  title: string;
  icon?: React.ReactNode;
  count?: number | null;
  page: number;
  pages: number;
  onPage: (p: number) => void;
  children: React.ReactNode;
  hideTitle?: boolean;
  /** Rendered right-aligned, only when total exceeds what is shown. */
  viewAll?: { text: string; onClick: () => void; total: number; shown: number } | null;
  hidePager?: boolean;
}) {
  const showViewAll = Boolean(viewAll && viewAll.total > viewAll.shown);
  return (
    <section aria-label={title} className="mt-8">
      {!hideTitle && (
        <div className="flex flex-wrap items-center gap-3">
          <h2
            className="font-semibold"
            style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem", color: "var(--navy-900)", fontSize: "1.125rem" }}
          >
            {icon && (
              <span aria-hidden="true" style={{ display: "inline-flex" }}>
                {icon}
              </span>
            )}
            {title}
            {count !== null && count !== undefined && (
              <span style={{ color: "var(--text-muted)", fontSize: "0.9375rem", fontWeight: 400 }}>
                {count}
              </span>
            )}
          </h2>
          <div className="ml-auto flex flex-wrap items-center gap-3">
            {showViewAll && viewAll && (
              <button
                type="button"
                onClick={viewAll.onClick}
                className="font-semibold"
                style={{ color: "var(--blue-700)", background: "none", border: "none", cursor: "pointer", fontSize: "1rem", whiteSpace: "nowrap" }}
              >
                {viewAll.text}
              </button>
            )}
            {!hidePager && pages > 1 && <Pager page={page} pages={pages} onPage={onPage} />}
          </div>
        </div>
      )}
      {hideTitle && !hidePager && pages > 1 && (
        <div className="flex items-center justify-end">
          <Pager page={page} pages={pages} onPage={onPage} />
        </div>
      )}
      <div className="mt-2">{children}</div>
    </section>
  );
}

function DatasetRow({ card, tokens }: { card: Card; tokens: string[] }) {
  const dept = card.department_display ?? card.department ?? "";
  const deptName = dept.trim() ? humanizeRaw(dept) : null;
  const description =
    (card.tables ?? []).map((t) => t.description?.trim()).find(Boolean) ??
    card.description?.trim() ??
    "";
  const updated = formatUpdatedAt(card.updated_at);
  return (
    <li
      className="result-card"
      style={{ border: "0.5px solid var(--border)", borderRadius: 8, padding: "13px 14px", background: "var(--bg)" }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.5rem" }}>
        {deptName ? (
          <span style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem", color: "var(--text-muted)", fontSize: "0.8125rem" }}>
            <DeptIcon />
            {deptName}
          </span>
        ) : (
          <span />
        )}
        <span style={{ marginLeft: "auto", fontSize: "0.75rem", fontWeight: 600, letterSpacing: "0.04em", textTransform: "uppercase", color: "var(--text-muted)", whiteSpace: "nowrap" }}>
          {t("typeDataset")}
        </span>
      </div>
      <div className="mt-1" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
        <span aria-hidden="true" style={{ display: "inline-flex", color: "var(--blue-700)" }}>
          <DatabaseIcon />
        </span>
        <Link
          to={`/datasets/${encodeURIComponent(card.dataset)}`}
          className="stretched-link"
          style={{ color: "var(--blue-700)", fontSize: "0.9375rem", fontWeight: 500, overflowWrap: "anywhere" }}
        >
          <Highlight text={humanizeRaw(card.name)} tokens={tokens} />
        </Link>
      </div>
      {description ? (
        <p className="clamp-2 mt-1" style={{ color: "var(--text)", fontSize: "0.9375rem" }}>
          {description}
        </p>
      ) : null}
      <div className="mt-2 flex flex-wrap gap-2">
        <span className="badge badge-neutral">
          {card.table_count} {card.table_count === 1 ? "table" : "tables"}
        </span>
        {updated && <span className="badge badge-neutral">{updated}</span>}
      </div>
    </li>
  );
}

function classificationBadgeClass(level: string): string {
  switch (level) {
    case "Public":
      return "badge-public";
    case "Internal":
      return "badge-department";
    case "Restricted":
      return "badge-restricted";
    default:
      return "badge-confidential";
  }
}

function classificationLabel(level: "Public" | "Internal" | "Restricted" | "Sensitive"): string {
  switch (level) {
    case "Public":
      return t("classificationPublic");
    case "Internal":
      return t("classificationInternal");
    case "Restricted":
      return t("classificationRestricted");
    case "Sensitive":
      return t("classificationSensitive");
  }
}

function TableResultCard({
  hit, datasetDisplay, deptDisplay, multiDept, tokens,
}: {
  hit: TableHit;
  datasetDisplay: string;
  deptDisplay: string | null;
  multiDept: boolean;
  tokens: string[];
}) {
  // Column count and personal-data counts are hidden until the search API
  // exposes them (TableHit has no column data); never invented here.
  // Classification renders only when the API provides data_classification.
  const level = normalizeClassification(hit.data_classification);
  const chips: React.ReactNode[] = [];
  if (level) {
    chips.push(
      <span key="classification" className={`badge ${classificationBadgeClass(level)}`}>
        {classificationLabel(level)}
      </span>,
    );
  }
  return (
    <ClickableLi
      url={tableUrl(hit.dataset, hit.name)}
      itemStyle={{
        border: "0.5px solid var(--border)",
        borderRadius: 8,
        borderLeft: "3px solid var(--blue-700)",
        padding: "12px 14px",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.5rem" }}>
        <div className="min-w-0 flex-1">
          <Crumbs
            trail={
              multiDept && deptDisplay
                ? [{ label: humanizeRaw(deptDisplay) }, { label: datasetDisplay }]
                : [{ label: datasetDisplay }]
            }
          />
        </div>
        <span style={{ marginLeft: "auto", fontSize: "0.75rem", fontWeight: 600, letterSpacing: "0.04em", textTransform: "uppercase", color: "var(--text-muted)", whiteSpace: "nowrap" }}>
          {t("typeTable")}
        </span>
      </div>
      <div className="mt-1" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
        <span aria-hidden="true" style={{ display: "inline-flex", color: "var(--blue-700)" }}>
          <TableIcon />
        </span>
        <span style={{ color: "var(--blue-700)", fontSize: "0.9375rem", fontWeight: 500, overflowWrap: "anywhere" }}>
          <Highlight text={humanizeRaw(hit.name)} tokens={tokens} />
        </span>
      </div>
      {hit.description ? (
        <p className="clamp-2 mt-1" style={{ color: "var(--text)", fontSize: "0.9375rem" }}>
          {hit.description}
        </p>
      ) : null}
      {chips.length > 0 && <div className="mt-2 flex flex-wrap gap-2">{chips}</div>}
      {(hit.matched_in?.length || hit.matched_columns?.length) ? (
        <p className="mt-1" style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
          {t("matchedIn")}: {(hit.matched_in ?? []).join(", ")}
          {(hit.matched_columns ?? []).length > 0 && (
            <>
              {" ("}
              {(hit.matched_columns ?? []).map((col, i) => (
                <span key={`${col}-${i}`}>
                  {i > 0 && ", "}
                  <Highlight text={col} tokens={tokens} />
                </span>
              ))}
              {")"}
            </>
          )}
        </p>
      ) : null}
    </ClickableLi>
  );
}

function ColumnResultCard({
  col, datasetDisplay, deptDisplay, multiDept, tokens,
}: {
  col: ColumnHit;
  datasetDisplay: string;
  deptDisplay: string | null;
  multiDept: boolean;
  tokens: string[];
}) {
  const tableDisplay = col.table ? humanizeRaw(col.table) : "";
  const datasetShort = truncateLeft(datasetDisplay);
  const fullPath = multiDept && deptDisplay
    ? `${humanizeRaw(deptDisplay)} › ${datasetDisplay} › ${tableDisplay}`
    : `${datasetDisplay} › ${tableDisplay}`;
  const tableTo = tableUrl(col.dataset, col.table);
  return (
    <li
      style={{
        background: "var(--bg-alt)",
        border: "0.5px solid var(--border)",
        borderRadius: 8,
        padding: "11px 12px",
        minWidth: 0,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.5rem" }}>
        <span style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem", minWidth: 0, color: "var(--text)", fontFamily: MONO_FONT, fontSize: "0.9375rem", fontWeight: 600, overflowWrap: "anywhere" }}>
          <span aria-hidden="true" style={{ display: "inline-flex", color: "var(--text-muted)" }}>
            <ColumnsIcon />
          </span>
          <Highlight text={col.name ?? ""} tokens={tokens} />
        </span>
        {col.dataType && (
          <span className="badge badge-neutral" style={{ marginLeft: "auto", whiteSpace: "nowrap" }}>
            {col.dataType}
          </span>
        )}
      </div>
      <div className="mt-1">
        <Crumbs
          fullPath={fullPath}
          trail={[
            ...(multiDept && deptDisplay ? [{ label: humanizeRaw(deptDisplay) }] : []),
            { label: datasetShort, title: datasetDisplay },
            ...(tableTo && tableDisplay
              ? [{ label: tableDisplay, to: tableTo, title: tableDisplay }]
              : tableDisplay
                ? [{ label: tableDisplay }]
                : []),
          ]}
        />
      </div>
    </li>
  );
}
