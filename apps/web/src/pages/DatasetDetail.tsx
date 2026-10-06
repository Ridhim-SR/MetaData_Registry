import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import { getDataset, requestAccess } from "../api/registry";
import { humanizeRaw } from "../utils/format";
import { ApiError } from "../api/client";
import { AccessBadge } from "../components/registry/AccessBadge";
import { EmptyBlock, ErrorBlock, LoadingBlock } from "../components/registry/StateBlocks";
import { useAuth } from "../contexts/AuthContext";

function LockedPanel({ datasetFqn }: { datasetFqn: string }) {
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
        Sign in to view schema
      </h2>
      <p className="mx-auto mt-2 max-w-md text-sm" style={{ color: "var(--text-muted)", fontSize: "0.9375rem" }}>
        This dataset&apos;s tables and columns are visible to authorized users. Sign in
        with your department account, or request access from the owning department.
      </p>
      <div className="mt-4">
        {state === "sent" ? (
          <p className="text-sm font-medium" role="status" style={{ color: "var(--public-fg)" }}>
            Access requested. The owning department will review your request.
          </p>
        ) : (
          <button
            onClick={onRequest}
            disabled={state === "sending"}
            className="btn-primary disabled:opacity-60"
            style={{ fontSize: "0.9375rem" }}
          >
            {state === "sending" ? "Requesting…" : "Request Access"}
          </button>
        )}
      </div>
      {state === "error" && (
        <p className="mt-2 text-sm" role="alert" style={{ color: "var(--confid-fg)" }}>
          Could not send the request. Please try again.
        </p>
      )}
    </div>
  );
}

export function DatasetDetailPage() {
  const { datasetFqn } = useParams<{ datasetFqn: string }>();
  const fqn = datasetFqn ? decodeURIComponent(datasetFqn) : "";

  const query = useQuery({
    queryKey: ["registry-dataset", fqn],
    queryFn: () => getDataset(fqn),
    enabled: Boolean(fqn),
    retry: false,
  });

  return (
    <div className="mx-auto w-full max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      <Link
        to="/explore"
        className="mb-4 inline-block text-sm font-medium"
        style={{ color: "var(--blue-700)" }}
      >
        ← Back to catalog
      </Link>

      {query.isPending && <LoadingBlock lines={5} />}

      {query.error && query.error instanceof ApiError && query.error.status === 404 && (
        <EmptyBlock
          title="Dataset not found."
          body="It may have been removed, or you may not have permission to view it."
          action={
            <Link to="/explore" className="btn-secondary" style={{ fontSize: "0.875rem" }}>
              Back to catalog
            </Link>
          }
        />
      )}

      {query.error && query.error instanceof ApiError && query.error.status === 403 && (
        <EmptyBlock
          title="You do not have permission to view this metadata."
          body="If you need it for your work, you can request access from the owning department."
          action={
            <Link to="/explore" className="btn-secondary" style={{ fontSize: "0.875rem" }}>
              Back to catalog
            </Link>
          }
        />
      )}

      {query.error && !(query.error instanceof ApiError && (query.error.status === 403 || query.error.status === 404)) && (
        <ErrorBlock message="Unable to load this dataset. Please try again." onRetry={() => query.refetch()} />
      )}

      {query.data && (
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
                <p className="mt-1 text-sm" style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
                  {query.data.dataset}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <AccessBadge level={query.data.access_level} />
                <span className="badge badge-neutral">
                  {query.data.table_count} {query.data.table_count === 1 ? "table" : "tables"}
                </span>
              </div>
            </div>
            {query.data.description ? (
              <p className="mt-4 text-sm" style={{ color: "var(--text)", fontSize: "0.9375rem" }}>
                {query.data.description}
              </p>
            ) : (
              <p className="not-provided mt-4 text-sm" style={{ fontSize: "0.9375rem" }}>
                Not provided
              </p>
            )}
          </div>

          {query.data.locked || !query.data.tables ? (
            <LockedPanel datasetFqn={query.data.dataset} />
          ) : (
            <div>
              <h2 className="mt-8 font-semibold" style={{ color: "var(--navy-900)", fontSize: "1.125rem" }}>
                Tables ({query.data.tables.length})
              </h2>
              <div className="mt-3 grid grid-cols-1 gap-4 md:grid-cols-2">
                {query.data.tables.map((t) => (
                  <div
                    key={t.id}
                    className="p-4"
                    style={{
                      border: "1px solid var(--border)",
                      borderRadius: 6,
                      background: "var(--bg)",
                    }}
                  >
                    <div className="font-semibold" style={{ color: "var(--navy-900)", fontSize: "1rem" }}>
                      {t.name || "Not provided"}
                    </div>
                    {t.description ? (
                      <div className="clamp-2 mt-1 text-sm" style={{ color: "var(--text)", fontSize: "0.9375rem" }}>
                        {t.description}
                      </div>
                    ) : (
                      <div className="not-provided mt-1 text-sm" style={{ fontSize: "0.9375rem" }}>
                        Not provided
                      </div>
                    )}
                    <div className="mt-3" style={{ color: "var(--text-muted)", fontSize: "0.8125rem" }}>
                      {t.columns?.length ?? 0} columns
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
