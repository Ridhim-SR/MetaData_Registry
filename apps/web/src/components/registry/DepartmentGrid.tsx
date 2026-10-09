import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { listDepartments } from "../../api/registry";
import { t } from "../../i18n";
import { humanizeRaw } from "../../utils/format";
import { EmptyBlock, ErrorBlock, Skeleton } from "./StateBlocks";

const icons = ["🌾", "🏥", "🏗", "💧", "🏭", "📚", "🏘", "🗺"];
function iconFor(index: number) {
  return icons[index % icons.length];
}

export function DepartmentGrid({ compact = false }: { compact?: boolean }) {
  const query = useQuery({ queryKey: ["registry-departments"], queryFn: listDepartments });
  const [searchText, setSearchText] = useState("");
  const [sort, setSort] = useState<"name" | "datasets">("name");

  const all = query.data ? [...query.data.items] : [];
  // Home: most datasets first. Directory page: name A-Z by default.
  const sortedTop = [...all].sort((a, b) => b.dataset_count - a.dataset_count);
  // Show the loader on every fetch so stale tiles never flash as current.
  const loading = query.isPending || query.isFetching;
  const total = query.data?.total ?? 0;

  const needle = searchText.trim().toLowerCase();
  const isSearching = needle.length > 0;
  const filtered = isSearching
    ? all.filter((d) => (d.display_name ?? "").toLowerCase().includes(needle))
    : all;
  const directoryShown = [...filtered].sort((a, b) =>
    sort === "name"
      ? (a.display_name || "").localeCompare(b.display_name || "")
      : b.dataset_count - a.dataset_count,
  );
  const shown = compact ? sortedTop.slice(0, 8) : directoryShown;
  const visibleDatasets = filtered.reduce((n, d) => n + d.dataset_count, 0);
  const showSort = !compact && total >= 4;
  const deptWord = (n: number) => t(n === 1 ? "deptCountOne" : "deptCountOther", { count: String(n) });
  const datasetWord = (n: number) =>
    t(n === 1 ? "datasetCountOne" : "datasetCountOther", { count: String(n) });

  return (
    <section
      aria-label="Top departments"
      className="page-container mx-auto w-full max-w-7xl px-4 py-10 sm:px-6 lg:px-8"
      style={compact ? undefined : { paddingTop: "24px" }}
    >
      {compact ? (
        <div>
          <div
            className="gap-3"
            style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}
          >
            <h2 className="font-semibold" style={{ color: "var(--navy-900)", fontSize: "1.375rem" }}>
              Top Departments
            </h2>
            {total > 0 && (
              <Link
                to="/departments"
                className="font-semibold"
                aria-label="View all departments"
                style={{ color: "var(--blue-700)", fontSize: "1rem", whiteSpace: "nowrap" }}
              >
                View all →
              </Link>
            )}
          </div>
          <p className="mt-1 text-sm" style={{ color: "var(--text-muted)", fontSize: "0.9375rem" }}>
            Departments with the most published datasets.
          </p>
        </div>
      ) : (
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm" style={{ color: "var(--text-muted)", fontSize: "0.9375rem" }}>
            {isSearching
              ? t("deptSearchCount", { shown: String(filtered.length), total: String(total) })
              : (
                <>
                  {deptWord(filtered.length)}
                  {" · "}
                  {datasetWord(visibleDatasets)}
                </>
              )}
          </p>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <div className="relative w-full sm:w-[300px]">
              <label htmlFor="directory-dept-search" className="sr-only">
                {t("deptFind")}
              </label>
              <span
                aria-hidden="true"
                style={{
                  position: "absolute",
                  left: "0.6rem",
                  top: "50%",
                  transform: "translateY(-50%)",
                  display: "inline-flex",
                  color: "var(--text-muted)",
                  pointerEvents: "none",
                }}
              >
                <svg
                  width="15"
                  height="15"
                  viewBox="0 0 16 16"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.75"
                >
                  <circle cx="7" cy="7" r="5" />
                  <path d="M11 11l3.5 3.5" />
                </svg>
              </span>
              <input
                id="directory-dept-search"
                type="search"
                value={searchText}
                onChange={(e) => setSearchText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Escape" && searchText) setSearchText("");
                }}
                placeholder={t("deptFindPlaceholder")}
                className="dept-search-input w-full"
                style={{
                  border: "1px solid var(--text-muted)",
                  borderRadius: 6,
                  padding: "0.35rem 0.6rem",
                  paddingLeft: "2rem",
                  paddingRight: searchText ? "1.75rem" : undefined,
                  fontSize: "0.875rem",
                  color: "var(--text)",
                  background: "var(--bg)",
                }}
              />
              {searchText && (
                <button
                  type="button"
                  onClick={() => setSearchText("")}
                  aria-label={t("deptClearSearch")}
                  style={{
                    position: "absolute",
                    right: "0.35rem",
                    top: "50%",
                    transform: "translateY(-50%)",
                    background: "none",
                    border: "none",
                    cursor: "pointer",
                    color: "var(--text-muted)",
                    fontSize: "0.875rem",
                    padding: "0 0.25rem",
                  }}
                >
                  ✕
                </button>
              )}
            </div>
            {showSort && (
              <>
                <label htmlFor="directory-dept-sort" className="sr-only">
                  {t("deptSortLabel")}
                </label>
                <select
                  id="directory-dept-sort"
                  value={sort}
                  onChange={(e) => setSort(e.target.value as "name" | "datasets")}
                  className="w-full sm:w-auto"
                  style={{
                    border: "1px solid var(--border)",
                    borderRadius: 6,
                    padding: "0.35rem 0.6rem",
                    fontSize: "0.875rem",
                    color: "var(--text)",
                    background: "var(--bg)",
                  }}
                >
                  <option value="name">{t("deptSortName")}</option>
                  <option value="datasets">{t("deptSortMostDatasets")}</option>
                </select>
              </>
            )}
          </div>
        </div>
      )}

      {loading && (
        <div
          className="mt-4"
          style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: "16px" }}
          role="status"
          aria-label="Loading departments"
        >
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
      )}
      {!loading && query.error && (
        <div className="mt-4">
          <ErrorBlock message="Unable to load departments. Please try again." onRetry={() => query.refetch()} />
        </div>
      )}
      {!loading && query.data && query.data.items.length === 0 && (
        <div className="mt-4">
          <EmptyBlock
            title="No departments published yet."
            body="Departments will appear here once metadata is published."
          />
        </div>
      )}
      {!loading && query.data && query.data.items.length > 0 && shown.length === 0 && (
        <div className="mt-4 text-center">
          <EmptyBlock
            title={t("deptNoMatch")}
            body={t("deptNoMatchHint")}
          />
        </div>
      )}
      {!loading && query.data && shown.length > 0 && (
        <ul
          className="mt-4"
          style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: "16px" }}
        >
          {shown.map((d, i) => (
            <li key={d.slug}>
              <Link
                to={`/departments/${encodeURIComponent(d.slug)}`}
                className="p-4"
                style={{
                  display: "flex",
                  flexDirection: "column",
                  height: "100%",
                  minHeight: "130px",
                  border: "1px solid var(--border)",
                  borderRadius: 6,
                  background: "var(--bg)",
                  textDecoration: "none",
                }}
              >
                <div aria-hidden style={{ color: "var(--saffron-text)", fontSize: "32px", lineHeight: 1 }}>
                  {iconFor(i)}
                </div>
                <div className="mt-2 font-semibold" style={{ color: "var(--navy-900)", fontSize: "1rem" }}>
                  {humanizeRaw(d.display_name)}
                </div>
                <div
                  className="text-sm"
                  style={{ marginTop: "auto", paddingTop: "0.25rem", color: "var(--text-muted)", fontSize: "0.875rem" }}
                >
                  {d.dataset_count} {d.dataset_count === 1 ? "dataset" : "datasets"}
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
      {compact && total > 8 && (
        <p className="mt-4 text-center">
          <Link
            to="/departments"
            className="btn-secondary"
            aria-label="View all departments"
            style={{ fontSize: "0.9375rem" }}
          >
            View all →
          </Link>
        </p>
      )}
    </section>
  );
}
