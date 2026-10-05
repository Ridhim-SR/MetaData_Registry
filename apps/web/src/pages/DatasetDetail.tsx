import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { getDataset } from "../api/registry";
import { ApiError } from "../api/client";
import { AccessBadge } from "../components/registry/AccessBadge";
import { EmptyBlock, ErrorBlock, LoadingBlock } from "../components/registry/StateBlocks";

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
      <Link to="/explore" className="mb-4 inline-block text-sm font-medium text-slate-900 underline">
        ← Back to catalog
      </Link>

      {query.isPending && <LoadingBlock lines={5} />}

      {query.error && query.error instanceof ApiError && query.error.status === 401 && (
        <EmptyBlock
          title="This metadata requires department access."
          body="Sign in with your department account to view this dataset."
          action={
            <Link
              to="/login"
              className="inline-flex rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700"
            >
              Sign In
            </Link>
          }
        />
      )}

      {query.error && query.error instanceof ApiError && query.error.status === 403 && (
        <EmptyBlock
          title="You do not have permission to view this metadata."
          body="If you need it for your work, you can request access from the owning department."
          action={
            <Link
              to="/explore"
              className="inline-flex rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-900 hover:bg-slate-100"
            >
              Back to catalog
            </Link>
          }
        />
      )}

      {query.error && !(query.error instanceof ApiError && (query.error.status === 401 || query.error.status === 403)) && (
        <ErrorBlock message="Unable to load this dataset. Please try again." onRetry={() => query.refetch()} />
      )}

      {query.data && (
        <div>
          <div className="rounded-lg border border-slate-200 bg-white p-6">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-sm text-slate-500">{query.data.service} / {query.data.database}</p>
                <h1 className="mt-1 text-2xl font-bold text-slate-900">{query.data.name}</h1>
                <p className="mt-1 text-sm text-slate-500">Department: {query.data.department ?? query.data.service}</p>
              </div>
              <div className="flex items-center gap-2">
                <AccessBadge level={query.data.access_level} />
                <span className="rounded-md bg-slate-100 px-3 py-1 text-sm text-slate-600">
                  {query.data.table_count} {query.data.table_count === 1 ? "table" : "tables"}
                </span>
              </div>
            </div>
          </div>

          <h2 className="mt-8 text-lg font-semibold text-slate-900">Tables</h2>
          <div className="mt-3 grid grid-cols-1 gap-4 md:grid-cols-2">
            {query.data.tables.map((t) => (
              <Link
                key={t.id}
                to={`/explore/${t.id}`}
                className="rounded-lg border border-slate-200 bg-white p-4 transition-shadow hover:shadow-md"
              >
                <div className="text-lg font-semibold text-slate-900">{t.name}</div>
                <div className="mt-1 line-clamp-2 text-sm text-slate-600">
                  {t.description || "No description"}
                </div>
                <div className="mt-3 text-xs text-slate-500">{t.columns?.length ?? 0} columns</div>
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
