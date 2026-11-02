import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import { getDataset, requestAccess, type DatasetCard, type DatasetInfo } from "../api/registry";
import { displayName } from "../api/auth";
import {
  catLabel,
  classificationBadgeClass,
  datasetCompletenessItems,
  humanizeRaw,
  normalizeClassification,
  tableCompletenessItems,
} from "../utils/format";
import { t, useLanguage } from "../i18n";
import { ApiError } from "../api/client";
import { EmptyBlock, ErrorBlock, LoadingBlock } from "../components/registry/StateBlocks";
import { CatBadge } from "../components/registry/CatBadge";
import { CompletenessMeter } from "../components/registry/CompletenessCard";
import { useAuth } from "../contexts/AuthContext";

function LockedPanel({ datasetFqn }: { datasetFqn: string }) {
  useLanguage();
  const { isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const [state, setState] = useState<"idle" | "sending" | "sent" | "error">("idle");

  const onRequest = async () => {
    if (!isAuthenticated) {
      navigate("/login", { state: { from: { pathname: `/datasets/${datasetFqn}` } } });
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

  return (
    <div
      className="mt-6 p-6 text-center"
      style={{ border: "1px solid var(--border)", borderRadius: 6, background: "var(--bg-alt)" }}
    >
      <h2 className="font-semibold" style={{ color: "var(--navy-900)", fontSize: "1.125rem" }}>
        {t("signInViewSchema")}
      </h2>
      <p className="mx-auto mt-2 max-w-md text-sm" style={{ color: "var(--text-muted)", fontSize: "0.9375rem" }}>
        {t("lockedSchemaBody")}
      </p>
      <div className="mt-4">
        {state === "sent" ? (
          <p className="text-sm font-medium" role="status" style={{ color: "var(--public-fg)" }}>
            {t("accessRequested")}
          </p>
        ) : (
          <button
            onClick={onRequest}
            disabled={state === "sending"}
            className="btn-primary disabled:opacity-60"
            style={{ fontSize: "0.9375rem" }}
          >
            {state === "sending" ? t("requesting") : t("requestAccess")}
          </button>
        )}
      </div>
      {state === "error" && (
        <p className="mt-2 text-sm" role="alert" style={{ color: "var(--confid-fg)" }}>
          {t("requestFailed")}
        </p>
      )}
    </div>
  );
}

export function DatasetDetailPage() {
  useLanguage();
  const { datasetFqn } = useParams<{ datasetFqn: string }>();
  const fqn = datasetFqn ? decodeURIComponent(datasetFqn) : "";

  const query = useQuery({
    queryKey: ["registry-dataset", fqn],
    queryFn: () => getDataset(fqn),
    enabled: Boolean(fqn),
    retry: false,
  });

  // Loader on every fetch so a previous dataset never flashes as current.
  const loading = query.isPending || query.isFetching;

  return (
    <div className="page-container mx-auto w-full max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      <Link
        to="/explore"
        className="mb-4 inline-block text-sm font-medium"
        style={{ color: "var(--blue-700)" }}
      >
        {t("backToCatalogArrow")}
      </Link>

      {loading && <LoadingBlock lines={5} />}

      {!loading && query.error && query.error instanceof ApiError && query.error.status === 401 && (
        <EmptyBlock
          title={t("signInViewDataset")}
          body={t("notPublicBody")}
          action={
            <Link to="/login" className="btn-primary" style={{ fontSize: "0.875rem" }}>
              {t("signIn")}
            </Link>
          }
        />
      )}

      {!loading && query.error && query.error instanceof ApiError && query.error.status === 404 && (
        <EmptyBlock
          title={t("datasetNotFound")}
          body={t("mayBeRemoved")}
          action={
            <Link to="/explore" className="btn-secondary" style={{ fontSize: "0.875rem" }}>
              {t("backToCatalog")}
            </Link>
          }
        />
      )}

      {!loading && query.error && query.error instanceof ApiError && query.error.status === 403 && (
        <EmptyBlock
          title={t("noPermission")}
          body={t("noPermissionBody")}
          action={
            <Link to="/explore" className="btn-secondary" style={{ fontSize: "0.875rem" }}>
              {t("backToCatalog")}
            </Link>
          }
        />
      )}

      {!loading && query.error && !(query.error instanceof ApiError && (query.error.status === 401 || query.error.status === 403 || query.error.status === 404)) && (
        <ErrorBlock message={t("datasetLoadError")} onRetry={() => query.refetch()} />
      )}

      {!loading && query.data && (
        <div>
          <div
            className="p-6"
            style={{ border: "1px solid var(--border)", borderRadius: 6, background: "var(--bg)" }}
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-sm" style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
                  {humanizeRaw(query.data.department_display ?? query.data.department ?? null)}
                </p>
                <h1 className="mt-1 font-bold" style={{ color: "var(--navy-900)", fontSize: "1.5rem" }}>
                  {humanizeRaw(query.data.name)}
                </h1>
              </div>
              {/* Unlocked datasets already show the category in the facts box
                  and the count in "Tables (n)"; only locked teasers, which
                  have neither, show them here. */}
              {!query.data.locked && query.data.info && (
                <DatasetCompleteness card={query.data} info={query.data.info} />
              )}
              {query.data.locked && (
                <div className="flex items-center gap-2">
                  <CatBadge value={query.data.classification} />
                  <span className="badge badge-neutral">
                    {t(query.data.table_count === 1 ? "tableCountOne" : "tableCountOther", { count: query.data.table_count })}
                  </span>
                </div>
              )}
            </div>
            {query.data.description ? (
              <p className="mt-4 text-sm" style={{ color: "var(--text)", fontSize: "0.9375rem" }}>
                {query.data.description}
              </p>
            ) : (
              <p className="not-provided mt-4 text-sm" style={{ fontSize: "0.9375rem" }}>
                {t("noDescription")}
              </p>
            )}
            {!query.data.locked && query.data.info && <DatasetFacts info={query.data.info} />}
          </div>

          {query.data.locked || !query.data.tables ? (
            <LockedPanel datasetFqn={query.data.dataset} />
          ) : (
            <div>
              <h2 className="mt-8 font-semibold" style={{ color: "var(--navy-900)", fontSize: "1.125rem" }}>
                {t("tablesHeading", { count: query.data.tables.length })}
              </h2>
              <div className="mt-3 grid grid-cols-1 gap-4 md:grid-cols-2">
                {query.data.tables.map((t) => (
                  <TableCard
                    key={t.id}
                    dataset={query.data.dataset}
                    name={t.name}
                    columnCount={t.columns?.length ?? 0}
                  />
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Dataset-level facts (OM database custom properties and tags). Owner,
 * steward, frequency and timeline are the defaults every table inherits.
 * Without a dataset-level API flag or classification, they are summarized
 * over the tables this viewer can open.
 */
function DatasetFacts({ info }: { info: DatasetInfo }) {
  useLanguage();
  const level = normalizeClassification(info.data_classification);
  const api =
    info.api_available != null
      ? info.api_available
        ? t("yes")
        : t("no")
      : info.api_known === 0
        ? null
        : t("apiTablesCount", { count: String(info.api_tables), total: String(info.table_count) });
  return (
    <dl
      className="mt-4 grid grid-cols-1 gap-x-6 gap-y-2 p-4 sm:grid-cols-2"
      style={{ border: "1px solid var(--border)", borderRadius: 6, background: "var(--bg-alt)", fontSize: "0.9375rem" }}
    >
      <DatasetFact label={t("factOwner")} value={info.owner} />
      <DatasetFact label={t("factSteward")} value={info.steward} />
      <DatasetFact label={t("factFrequency")} value={info.frequency} />
      <DatasetFact label={t("timeline")} value={info.timeline} />
      <DatasetFact label={t("apiAvailable")} value={api} />
      <div>
        <dt className="metadata-fact-label">{t("dataClassification")}</dt>
        <dd className="mt-0.5">
          {catLabel(info.data_classification) ? (
            <CatBadge value={info.data_classification} />
          ) : level ? (
            <span
              className={`badge ${classificationBadgeClass(level)}`}
              title={info.data_classification_description ?? undefined}
            >
              {t(`classification${level}`)}
            </span>
          ) : (
            <span className="not-provided">{t("notProvided")}</span>
          )}
        </dd>
      </div>
      <DatasetFact label={t("factSchemaSource")} value={info.schema_source} />
    </dl>
  );
}

/**
 * Dataset-level completeness, shown only to admins and the dataset's owner
 * or steward. The facts box already shows what is "Not provided", so this is
 * a compact meter; hovering lists what is missing. The table roll-up is shown
 * in the hover note but deliberately kept out of the percentage.
 */
function DatasetCompleteness({ card, info }: { card: DatasetCard; info: DatasetInfo }) {
  const { lang } = useLanguage();
  const { isAuthenticated, user } = useAuth();
  const canEdit = useMemo(() => {
    if (!isAuthenticated || !user) return false;
    if (user.role === "admin") return true;
    const tokens = [user.username, user.email, displayName(user)]
      .filter(Boolean)
      .map((s) => s.toLowerCase());
    return [info.owner, info.steward].some(
      (c) => typeof c === "string" && c.trim() !== "" && tokens.includes(c.toLowerCase()),
    );
  }, [isAuthenticated, user, info]);

  // Item labels are translated, so recompute on a language switch too.
  const items = useMemo(
    () => datasetCompletenessItems(card.description, info),
    [card.description, info, lang],
  );
  const tables = card.tables ?? [];
  const fullTables = useMemo(
    () => tables.filter((tb) => tableCompletenessItems(tb).every((i) => i.score >= 1)).length,
    [tables],
  );

  if (!canEdit) return null;
  return (
    <CompletenessMeter
      label={t("datasetCompletenessLabel")}
      items={items}
      note={
        tables.length > 0
          ? t("tablesFullyDocumented", { done: String(fullTables), total: String(tables.length) })
          : null
      }
    />
  );
}

function DatasetFact({ label, value }: { label: string; value: string | null | undefined }) {
  const text = value && value.trim() ? value : null;
  return (
    <div>
      <dt className="metadata-fact-label">{label}</dt>
      <dd className="mt-0.5" style={{ color: "var(--text)" }}>
        {text ?? <span className="not-provided">{t("notProvided")}</span>}
      </dd>
    </div>
  );
}

function TableCard({
  dataset,
  name,
  columnCount,
}: {
  dataset: string;
  name: string;
  columnCount: number;
}) {
  const navigate = useNavigate();
  const url = `/datasets/${encodeURIComponent(dataset)}/tables/${encodeURIComponent(name)}`;
  return (
    <div
      role="link"
      tabIndex={0}
      aria-label={t("openTable", { name })}
      className="p-4"
      style={{
        border: "1px solid var(--border)",
        borderRadius: 6,
        background: "var(--bg)",
        cursor: "pointer",
      }}
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
        e.currentTarget.style.background = "var(--bg)";
      }}
    >
      <div className="font-semibold" style={{ color: "var(--navy-900)", fontSize: "1rem" }}>
        {humanizeRaw(name) || t("notProvided")}
      </div>
      <div className="mt-3" style={{ color: "var(--text-muted)", fontSize: "0.8125rem" }}>
        {t(columnCount === 1 ? "colCountOne" : "colCountOther", { count: columnCount })}
      </div>
    </div>
  );
}
