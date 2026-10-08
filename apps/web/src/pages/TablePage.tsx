import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  downloadTableDictionary,
  getDataset,
  getRegistryTable,
  getTableLineage,
  requestAccess,
} from "../api/registry";
import { ApiError } from "../api/client";
import { AccessBadge } from "../components/registry/AccessBadge";
import { EmptyBlock, ErrorBlock, LoadingBlock } from "../components/registry/StateBlocks";
import { humanizeRaw, isSensitiveTag, readableTag } from "../utils/format";
import { useAuth } from "../contexts/AuthContext";

type Tab = "schema" | "about" | "docs" | "lineage";

const COLS_PER_PAGE = 50;

function formatDate(ms: number | null | undefined): string | null {
  if (!ms) return null;
  try {
    return new Date(ms).toLocaleDateString("en-IN", {
      day: "2-digit",
      month: "short",
      year: "numeric",
    });
  } catch {
    return null;
  }
}

function AccessStateButton({ datasetFqn, tableName }: { datasetFqn: string; tableName: string }) {
  const { isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const [state, setState] = useState<"idle" | "sending" | "sent" | "error">("idle");

  const onRequest = async () => {
    if (!isAuthenticated) {
      navigate("/login", {
        state: { from: { pathname: `/datasets/${datasetFqn}/tables/${tableName}` } },
      });
      return;
    }
    setState("sending");
    try {
      await requestAccess(datasetFqn);
      setState("sent");
    } catch {
      setState("error");
    }
  };

  if (state === "sent") {
    return (
      <p className="text-sm font-medium" role="status" style={{ color: "var(--public-fg)" }}>
        Request pending — the owning department will review it.
      </p>
    );
  }
  return (
    <div>
      <button
        onClick={onRequest}
        disabled={state === "sending"}
        className="btn-primary disabled:opacity-60"
        style={{ fontSize: "0.9375rem" }}
      >
        {state === "sending" ? "Requesting…" : isAuthenticated ? "Request Access" : "Sign in to request access"}
      </button>
      {state === "error" && (
        <p className="mt-2 text-sm" role="alert" style={{ color: "var(--confid-fg)" }}>
          Could not send the request. Please try again.
        </p>
      )}
    </div>
  );
}

export function TablePage() {
  const { datasetFqn = "", tableName = "" } = useParams<{ datasetFqn: string; tableName: string }>();
  const [urlParams] = useSearchParams();
  const highlightColumn = urlParams.get("column") ?? "";
  const fqn = datasetFqn ? decodeURIComponent(datasetFqn) : "";
  const tname = tableName ? decodeURIComponent(tableName) : "";

  const [tab, setTab] = useState<Tab>("schema");
  const [colQuery, setColQuery] = useState("");
  const [colSort, setColSort] = useState<"name" | "type">("name");
  const [colPage, setColPage] = useState(1);
  const [csvState, setCsvState] = useState<"idle" | "sending" | "error">("idle");
  const highlightRef = useRef<HTMLTableRowElement>(null);

  const datasetQuery = useQuery({
    queryKey: ["registry-dataset", fqn],
    queryFn: () => getDataset(fqn),
    enabled: Boolean(fqn),
    retry: false,
  });

  const card = datasetQuery.data;
  const cardEntry = !card?.locked
    ? (card?.tables ?? []).find((t) => t.name === tname || t.id === tname)
    : undefined;

  const tableQuery = useQuery({
    queryKey: ["registry-table", cardEntry?.id],
    queryFn: () => getRegistryTable(cardEntry!.id),
    enabled: Boolean(cardEntry?.id),
    retry: false,
  });

  const table = tableQuery.data;
  const isFull = Boolean(table) && !(table as { locked?: boolean } | undefined)?.locked;

  const lineageQuery = useQuery({
    queryKey: ["registry-table-lineage", cardEntry?.id],
    queryFn: () => getTableLineage(cardEntry!.id),
    enabled: Boolean(cardEntry?.id) && isFull,
    retry: false,
  });

  const columns = useMemo(() => {
    let cols = [...(table?.columns ?? [])];
    const needle = colQuery.trim().toLowerCase();
    if (needle) cols = cols.filter((c) => (c.name || "").toLowerCase().includes(needle));
    cols.sort((a, b) =>
      colSort === "name"
        ? (a.name || "").localeCompare(b.name || "")
        : (a.dataTypeDisplay || a.dataType || "").localeCompare(b.dataTypeDisplay || b.dataType || ""),
    );
    return cols;
  }, [table, colQuery, colSort]);

  const colPages = Math.max(1, Math.ceil(columns.length / COLS_PER_PAGE));
  const safeColPage = Math.min(colPage, colPages);
  const visibleColumns = columns.slice((safeColPage - 1) * COLS_PER_PAGE, safeColPage * COLS_PER_PAGE);

  const sensitiveCount = useMemo(
    () => (table?.columns ?? []).filter((c) => (c.tags ?? []).some(isSensitiveTag)).length,
    [table],
  );

  useEffect(() => {
    setColPage(1);
  }, [colQuery, colSort, tname, fqn]);

  useEffect(() => {
    if (highlightColumn && highlightRef.current) {
      highlightRef.current.scrollIntoView({ block: "center" });
    }
  }, [highlightColumn, table, safeColPage]);

  const onDownloadCsv = async () => {
    if (!cardEntry?.id || csvState === "sending") return;
    setCsvState("sending");
    try {
      const csv = await downloadTableDictionary(cardEntry.id);
      const blob = new Blob([csv], { type: "text/csv" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${tname || "table"}_data_dictionary.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      setCsvState("idle");
    } catch {
      setCsvState("error");
    }
  };

  const deptDisplay = card?.department_display ?? card?.department ?? "";
  const otherTables = (card?.tables ?? []).filter((t) => t.name !== tname && t.id !== tname);
  // Loaders on every fetch so stale content never flashes as current.
  // NOTE: the table query is disabled until its parent dataset resolves;
  // a disabled query is perpetually "pending", so only treat it as loading
  // while actually enabled.
  const tableEnabled = Boolean(cardEntry?.id);
  const pageLoading =
    datasetQuery.isPending ||
    datasetQuery.isFetching ||
    (tableEnabled && (tableQuery.isPending || tableQuery.isFetching));
  const info = table && !table.locked ? table.info ?? null : null;
  const facts = table && !table.locked ? table.facts ?? null : null;
  const owners = table && !table.locked ? (table.owners ?? []) : [];
  const tableTags = table && !table.locked ? (table.tags ?? []) : [];
  const datasetTagNames: string[] = !isFull && card ? ((card as { tags?: string[] }).tags ?? []) : [];

  const hasAbout =
    Boolean(table?.description) || owners.length > 0 || tableTags.length > 0;
  const hasDocs =
    info != null &&
    (info.api_available != null ||
      Boolean(info.dataset_owner) ||
      Boolean(info.frequency) ||
      Boolean(info.timeline));
  const upstream: string[] = [];
  const downstream: string[] = [];
  for (const e of lineageQuery.data?.edges ?? []) {
    if (e.fromEntity?.fullyQualifiedName && e.toEntity?.fullyQualifiedName) {
      if (e.toEntity.fullyQualifiedName === table?.fullyQualifiedName) upstream.push(e.fromEntity.fullyQualifiedName);
      else if (e.fromEntity.fullyQualifiedName === table?.fullyQualifiedName) downstream.push(e.toEntity.fullyQualifiedName);
    }
  }
  const hasLineage = upstream.length > 0 || downstream.length > 0;

  const tabs: Array<{ id: Tab; label: string; show: boolean }> = [
    { id: "schema", label: "Schema", show: true },
    { id: "about", label: "About", show: hasAbout },
    { id: "docs", label: "Documentation", show: hasDocs },
    { id: "lineage", label: "Lineage", show: hasLineage },
  ];

  const describedCols = (table?.columns ?? []).filter((c) => (c.description ?? "").trim()).length;
  const totalCols = table?.columns?.length ?? 0;
  const colDescPct = totalCols === 0 ? 0 : Math.round((describedCols / totalCols) * 100);

  return (
    <div className="mx-auto w-full max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      <nav aria-label="Breadcrumb" className="mb-4 text-sm" style={{ color: "var(--text-muted)" }}>
        <Link to="/" style={{ color: "var(--blue-700)" }}>Home</Link>
        {" / "}
        <Link to="/explore" style={{ color: "var(--blue-700)" }}>Catalog</Link>
        {" / "}
        {card ? (
          <>
            <Link to={`/datasets/${encodeURIComponent(card.dataset)}`} style={{ color: "var(--blue-700)" }}>
              {humanizeRaw(card.name)}
            </Link>
            {" / "}
          </>
        ) : null}
        <span style={{ color: "var(--text)" }}>{humanizeRaw(tname) || "Table"}</span>
      </nav>

      {pageLoading && <LoadingBlock lines={6} />}

      {!pageLoading && datasetQuery.error && !(datasetQuery.error instanceof ApiError && datasetQuery.error.status === 404) && (
        <ErrorBlock message="Unable to load this table. Please try again." onRetry={() => datasetQuery.refetch()} />
      )}

      {!pageLoading && (datasetQuery.error instanceof ApiError && datasetQuery.error.status === 404) && (
        <EmptyBlock
          title="Table not found."
          body="It may have been removed, or you may not have permission to view it."
          action={
            <Link to="/explore" className="btn-secondary" style={{ fontSize: "0.875rem" }}>
              Back to catalog
            </Link>
          }
        />
      )}

      {!pageLoading && tableQuery.error && !(tableQuery.error instanceof ApiError && tableQuery.error.status === 404) && (
        <ErrorBlock message="Unable to load this table. Please try again." onRetry={() => tableQuery.refetch()} />
      )}

      {!pageLoading && (tableQuery.error instanceof ApiError && tableQuery.error.status === 404) && (
        <EmptyBlock
          title="Table not found."
          body="It may have been removed, or you may not have permission to view it."
          action={
            <Link to="/explore" className="btn-secondary" style={{ fontSize: "0.875rem" }}>
              Back to catalog
            </Link>
          }
        />
      )}

      {!pageLoading && card && (isFull || card.locked || !cardEntry) && (
        <div className="flex flex-col gap-6 lg:flex-row">
          <div className="min-w-0 flex-1">
            {/* HEADER */}
            <p className="text-sm" style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
              {humanizeRaw(deptDisplay || null)} &gt; {humanizeRaw(card?.name)}
            </p>
            <div className="mt-1 flex flex-wrap items-center gap-2">
              <h1 className="font-bold" style={{ color: "var(--navy-900)", fontSize: "1.5rem" }}>
                {humanizeRaw(isFull ? table?.name : tname)}
              </h1>
              <AccessBadge level={isFull ? table?.access_level : card.access_level} />
              {isFull && (
                <span className="badge badge-neutral">
                  {totalCols} {totalCols === 1 ? "column" : "columns"}
                </span>
              )}
              {isFull && (
                <span
                  className="badge badge-neutral"
                  title="Share of key metadata fields filled in"
                  style={{ fontSize: "0.8125rem" }}
                >
                  Metadata {colDescPct}%
                </span>
              )}
            </div>

            {/* FACTS STRIP */}
            <dl
              className="mt-4 grid grid-cols-1 gap-x-6 gap-y-2 p-4 sm:grid-cols-2"
              style={{ border: "1px solid var(--border)", borderRadius: 6, background: "var(--bg)", fontSize: "0.9375rem" }}
            >
              <Fact label="Owner" value={owners[0] ? owners[0].displayName || owners[0].name : null} />
              <Fact label="Data steward" value={facts?.steward ?? null} />
              <Fact label="Department contact" value={facts?.department_contact ?? null} />
              <Fact label="Last updated" value={facts?.updated_at ? formatDate(facts.updated_at) : null} />
              <Fact label="Update frequency" value={facts?.frequency ?? info?.frequency ?? null} />
              <Fact label="Source" value={facts?.source ?? null} />
            </dl>

            {/* TABS */}
            <div className="mt-6 flex gap-2" role="tablist" aria-label="Table sections">
              {tabs.filter((t) => t.show).map((t) => (
                <button
                  key={t.id}
                  role="tab"
                  aria-selected={tab === t.id}
                  onClick={() => setTab(t.id)}
                  className={tab === t.id ? "btn-primary" : "btn-secondary"}
                  style={{ padding: "0.4rem 1rem", fontSize: "0.875rem" }}
                >
                  {t.label}
                </button>
              ))}
            </div>

            {tab === "schema" && (
              <div className="mt-4" role="tabpanel" aria-label="Schema">
                {!isFull ? (
                  <div
                    className="p-6 text-center"
                    style={{ border: "1px solid var(--border)", borderRadius: 6, background: "var(--bg-alt)" }}
                  >
                    <h2 className="font-semibold" style={{ color: "var(--navy-900)", fontSize: "1.125rem" }}>
                      Request access to view columns
                    </h2>
                    <div className="mt-4 flex justify-center">
                      <AccessStateButton datasetFqn={card.dataset} tableName={tname} />
                    </div>
                  </div>
                ) : (
                  <div>
                    <div className="flex flex-col gap-2 sm:flex-row">
                      <label htmlFor="find-column" className="sr-only">Find a column</label>
                      <input
                        id="find-column"
                        type="search"
                        value={colQuery}
                        onChange={(e) => setColQuery(e.target.value)}
                        placeholder="Find a column…"
                        className="flex-1"
                        style={{ border: "1px solid var(--border)", borderRadius: 6, padding: "0.5rem 0.75rem", fontSize: "0.9375rem" }}
                      />
                      <label htmlFor="sort-columns" className="sr-only">Sort columns</label>
                      <select
                        id="sort-columns"
                        value={colSort}
                        onChange={(e) => setColSort(e.target.value as "name" | "type")}
                        style={{ border: "1px solid var(--border)", borderRadius: 6, padding: "0.5rem 0.75rem", fontSize: "0.9375rem", background: "var(--bg)" }}
                      >
                        <option value="name">Sort by name</option>
                        <option value="type">Sort by type</option>
                      </select>
                      <button
                        type="button"
                        onClick={onDownloadCsv}
                        disabled={csvState === "sending"}
                        className="btn-secondary disabled:opacity-60"
                        style={{ fontSize: "0.9375rem", whiteSpace: "nowrap" }}
                      >
                        {csvState === "sending" ? "Preparing…" : "Download data dictionary (CSV)"}
                      </button>
                    </div>
                    {csvState === "error" && (
                      <p className="mt-2 text-sm" role="alert" style={{ color: "var(--confid-fg)" }}>
                        Could not download the dictionary. Please try again.
                      </p>
                    )}
                    <p className="mt-3 text-sm" style={{ color: "var(--text-muted)", fontSize: "0.9375rem" }}>
                      {totalCols} {totalCols === 1 ? "column" : "columns"}
                      {sensitiveCount > 0 &&
                        ` · ${sensitiveCount} ${sensitiveCount === 1 ? "column contains" : "columns contain"} personal data`}
                    </p>
                    <div className="mt-2 overflow-x-auto" style={{ border: "1px solid var(--border)", borderRadius: 6 }}>
                      <table className="w-full text-sm" style={{ minWidth: 640 }}>
                        <thead style={{ background: "var(--bg-alt)", color: "var(--text-muted)" }}>
                          <tr>
                            <th scope="col" className="px-4 py-2 text-left font-medium">Column Name</th>
                            <th scope="col" className="px-4 py-2 text-left font-medium">Data Type</th>
                            <th scope="col" className="px-4 py-2 text-left font-medium">Description</th>
                            <th scope="col" className="px-4 py-2 text-left font-medium">Tags</th>
                          </tr>
                        </thead>
                        <tbody>
                          {visibleColumns.map((col) => {
                            const highlighted = highlightColumn && col.name === highlightColumn;
                            return (
                              <tr
                                key={col.name}
                                ref={highlighted ? highlightRef : undefined}
                                style={{
                                  borderTop: "1px solid var(--border)",
                                  background: highlighted ? "var(--blue-50)" : undefined,
                                }}
                              >
                                <td className="px-4 py-2 font-medium" style={{ color: "var(--text)" }}>{col.name}</td>
                                <td className="px-4 py-2">
                                  <span className="badge badge-neutral">
                                    {col.dataTypeDisplay || col.dataType || "Not provided"}
                                  </span>
                                </td>
                                <td className="px-4 py-2" style={{ color: "var(--text)" }}>
                                  {col.description || <span className="not-provided">No description</span>}
                                </td>
                                <td className="px-4 py-2">
                                  {(col.tags ?? []).length === 0 ? (
                                    <span className="not-provided">Not provided</span>
                                  ) : (
                                    <span style={{ color: "var(--text)" }}>
                                      {(col.tags ?? []).map(readableTag).join(", ")}
                                    </span>
                                  )}
                                </td>
                              </tr>
                            );
                          })}
                          {visibleColumns.length === 0 && (
                            <tr>
                              <td colSpan={4} className="px-4 py-3" style={{ color: "var(--text-muted)" }}>
                                No columns match.
                              </td>
                            </tr>
                          )}
                        </tbody>
                      </table>
                    </div>
                    {colPages > 1 && (
                      <div className="mt-3 flex items-center gap-2" style={{ fontSize: "0.875rem", color: "var(--text-muted)" }}>
                        <button type="button" disabled={safeColPage <= 1} onClick={() => setColPage(safeColPage - 1)}
                          className="btn-secondary" style={{ padding: "0.2rem 0.7rem", fontSize: "0.875rem" }}>
                          ‹ Prev
                        </button>
                        <span>Page {safeColPage} of {colPages}</span>
                        <button type="button" disabled={safeColPage >= colPages} onClick={() => setColPage(safeColPage + 1)}
                          className="btn-secondary" style={{ padding: "0.2rem 0.7rem", fontSize: "0.875rem" }}>
                          Next ›
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            {tab === "about" && hasAbout && (
              <div className="mt-4 space-y-4" role="tabpanel" aria-label="About">
                {table?.description && (
                  <p className="text-sm" style={{ color: "var(--text)", fontSize: "0.9375rem" }}>{table.description}</p>
                )}
                {owners.length > 0 && (
                  <div>
                    <h3 className="font-semibold" style={{ color: "var(--navy-900)", fontSize: "1rem" }}>Owners</h3>
                    <ul className="mt-1 list-disc pl-5 text-sm" style={{ color: "var(--text)" }}>
                      {owners.map((o, i) => (
                        <li key={o.id ?? o.fullyQualifiedName ?? o.name ?? i}>
                          {o.displayName || o.name || "Not provided"}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {tableTags.length > 0 && (
                  <div>
                    <h3 className="font-semibold" style={{ color: "var(--navy-900)", fontSize: "1rem" }}>Tags</h3>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {tableTags.map((t, i) => (
                        <span key={t.tagFQN ?? t.name ?? i} className="badge badge-neutral">
                          {readableTag(t)}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {tab === "docs" && hasDocs && info && (
              <dl className="mt-4 divide-y rounded-md" role="tabpanel" aria-label="Documentation"
                style={{ border: "1px solid var(--border)", background: "var(--bg)" }}>
                <DocRow label="Dataset owner" value={info.dataset_owner} hint="Who owns/is accountable for this dataset." />
                <DocRow label="Refresh frequency" value={info.frequency} hint="How often this dataset is refreshed." />
                <DocRow label="Timeline" value={info.timeline} hint="The period this dataset covers." />
                <DocRow
                  label="API available"
                  value={info.api_available == null ? null : info.api_available ? "Yes" : "No"}
                  hint="Whether this dataset is exposed via an API."
                />
              </dl>
            )}

            {tab === "lineage" && hasLineage && (
              <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2" role="tabpanel" aria-label="Lineage">
                <div className="p-4" style={{ border: "1px solid var(--border)", borderRadius: 6 }}>
                  <h3 className="font-semibold" style={{ color: "var(--navy-900)", fontSize: "1rem" }}>Upstream</h3>
                  <ul className="mt-2 space-y-1 text-sm" style={{ color: "var(--text)" }}>
                    {upstream.map((u) => <li key={u} style={{ overflowWrap: "anywhere" }}>{u}</li>)}
                  </ul>
                </div>
                <div className="p-4" style={{ border: "1px solid var(--border)", borderRadius: 6 }}>
                  <h3 className="font-semibold" style={{ color: "var(--navy-900)", fontSize: "1rem" }}>Downstream</h3>
                  <ul className="mt-2 space-y-1 text-sm" style={{ color: "var(--text)" }}>
                    {downstream.map((d) => <li key={d} style={{ overflowWrap: "anywhere" }}>{d}</li>)}
                  </ul>
                </div>
              </div>
            )}
          </div>

          {/* RIGHT PANEL */}
          <aside aria-label="Details" className="w-full shrink-0 lg:w-80" style={{ maxWidth: 320 }}>
            <div className="space-y-4">
              <div className="p-4" style={{ border: "1px solid var(--border)", borderRadius: 6, background: "var(--bg)" }}>
                <h2 className="font-semibold" style={{ color: "var(--navy-900)", fontSize: "1rem" }}>Access</h2>
                <div className="mt-2">
                  <AccessBadge level={isFull ? table?.access_level : card.access_level} />
                </div>
                <div className="mt-3">
                  {isFull ? (
                    <p className="text-sm font-medium" style={{ color: "var(--public-fg)" }}>You have access</p>
                  ) : (
                    <AccessStateButton datasetFqn={card.dataset} tableName={tname} />
                  )}
                </div>
              </div>

              <div className="p-4" style={{ border: "1px solid var(--border)", borderRadius: 6, background: "var(--bg)" }}>
                <h2 className="font-semibold" style={{ color: "var(--navy-900)", fontSize: "1rem" }}>Parent dataset</h2>
                <Link
                  to={`/datasets/${encodeURIComponent(card.dataset)}`}
                  className="mt-1 block font-medium"
                  style={{ color: "var(--blue-700)", fontSize: "0.9375rem" }}
                >
                  {humanizeRaw(card.name)}
                </Link>
                {otherTables.length > 0 && (
                  <>
                    <h3 className="mt-3 font-medium" style={{ color: "var(--text-muted)", fontSize: "0.8125rem" }}>
                      Other tables in this dataset
                    </h3>
                    <ul className="mt-1 space-y-1">
                      {otherTables.slice(0, 8).map((t) => (
                        <li key={t.id}>
                          <Link
                            to={`/datasets/${encodeURIComponent(card.dataset)}/tables/${encodeURIComponent(t.name)}`}
                            style={{ color: "var(--blue-700)", fontSize: "0.875rem" }}
                          >
                            {humanizeRaw(t.name)}
                          </Link>
                        </li>
                      ))}
                    </ul>
                  </>
                )}
              </div>

              {(tableTags.length > 0 || datasetTagNames.length > 0) && (
                <div className="p-4" style={{ border: "1px solid var(--border)", borderRadius: 6, background: "var(--bg)" }}>
                  <h2 className="font-semibold" style={{ color: "var(--navy-900)", fontSize: "1rem" }}>Tags</h2>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {isFull
                      ? tableTags.map((t, i) => (
                        <span key={t.tagFQN ?? t.name ?? i} className="badge badge-neutral">
                          {readableTag(t)}
                        </span>
                      ))
                      : datasetTagNames.map((t) => (
                        <span key={t} className="badge badge-neutral">{t}</span>
                      ))}
                  </div>
                </div>
              )}

              <div className="p-4" style={{ border: "1px solid var(--border)", borderRadius: 6, background: "var(--bg)" }}>
                <h2 className="font-semibold" style={{ color: "var(--navy-900)", fontSize: "1rem" }}>
                  Metadata completeness
                </h2>
                <ul className="mt-2 space-y-1 text-sm" style={{ fontSize: "0.875rem" }}>
                  <ChecklistItem done={Boolean(table?.description)} label="Description" />
                  <ChecklistItem done={owners.length > 0} label="Owner" />
                  <ChecklistItem done={Boolean(facts?.steward)} label="Steward" />
                  <ChecklistItem done={describedCols === totalCols && totalCols > 0} label={`Column descriptions ${describedCols}/${totalCols}`} />
                </ul>
              </div>
            </div>
          </aside>
        </div>
      )}
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string | null | undefined }) {
  const text = value && String(value).trim() ? String(value) : null;
  return (
    <div>
      <dt style={{ color: "var(--text-muted)", fontSize: "0.8125rem" }}>{label}</dt>
      <dd className="mt-0.5" style={{ color: "var(--text)", fontSize: "0.9375rem" }}>
        {text ?? <span className="not-provided">Not provided</span>}
      </dd>
    </div>
  );
}

function DocRow({ label, value, hint }: { label: string; value: string | null | undefined; hint: string }) {
  return (
    <div className="px-4 py-3">
      <dt className="text-sm font-medium" style={{ color: "var(--text)" }}>{label}</dt>
      <dd style={{ color: "var(--text-muted)", fontSize: "0.8125rem" }}>{hint}</dd>
      <dd className="mt-1 text-sm" style={{ color: "var(--text)" }}>
        {value || <span className="not-provided">Not provided</span>}
      </dd>
    </div>
  );
}

function ChecklistItem({ done, label }: { done: boolean; label: string }) {
  return (
    <li className="flex items-center gap-2" style={{ color: done ? "var(--text)" : "var(--text-muted)" }}>
      <span aria-hidden style={{ color: done ? "var(--public-fg)" : "var(--text-muted)" }}>
        {done ? "✓" : "○"}
      </span>
      {label}
    </li>
  );
}
