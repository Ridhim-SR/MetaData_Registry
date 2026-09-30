import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { getRegistryTable, requestAccess } from "../api/registry";
import { ApiError } from "../api/client";
import { AccessBadge } from "../components/registry/AccessBadge";
import { EmptyBlock, ErrorBlock, LoadingBlock } from "../components/registry/StateBlocks";
import { useAuth } from "../contexts/AuthContext";

function crumbs(fqn: string) {
  return fqn.split(".");
}

export function TableDetailPage() {
  const { tableId } = useParams<{ tableId: string }>();
  const { isAuthenticated } = useAuth();
  const [reqState, setReqState] = useState<"idle" | "sending" | "sent" | "error">("idle");

  const query = useQuery({
    queryKey: ["registry-table", tableId],
    queryFn: () => getRegistryTable(tableId!),
    enabled: Boolean(tableId),
    retry: false,
  });

  const onRequest = async (fqn: string) => {
    setReqState("sending");
    try {
      await requestAccess(fqn);
      setReqState("sent");
    } catch {
      setReqState("error");
    }
  };

  return (
    <div className="mx-auto w-full max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      <Link to="/explore" className="mb-4 inline-block text-sm font-medium text-slate-900 underline">
        ← Back to catalog
      </Link>

      {query.isPending && <LoadingBlock lines={6} />}

      {query.error && query.error instanceof ApiError && query.error.status === 401 && (
        <EmptyBlock
          title="This metadata requires department access."
          body="Sign in with your department account to view this table."
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
          body="If you need it for your work, request access and the owning department will review it."
          action={
            isAuthenticated ? (
              <span className="text-sm text-slate-500">Use the dataset page to request access.</span>
            ) : (
              <Link
                to="/login"
                className="inline-flex rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700"
              >
                Sign In
              </Link>
            )
          }
        />
      )}

      {query.error && !(query.error instanceof ApiError && (query.error.status === 401 || query.error.status === 403)) && (
        <ErrorBlock message="Unable to load this table. Please try again." onRetry={() => query.refetch()} />
      )}

      {query.data && (
        <div>
          <div className="rounded-lg border border-slate-200 bg-white p-6">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <div className="text-sm text-slate-500">{crumbs(query.data.fullyQualifiedName).slice(0, -1).join(" / ")}</div>
                <h1 className="mt-1 text-2xl font-bold text-slate-900">{query.data.name}</h1>
              </div>
              <div className="flex items-center gap-2">
                <AccessBadge level={query.data.access_level} />
                <span className="rounded-md bg-slate-100 px-3 py-1 text-sm text-slate-600">
                  {query.data.columns?.length ?? 0} columns
                </span>
              </div>
            </div>
            <p className="mt-4 text-sm text-slate-600">{query.data.description || "No description"}</p>
            {query.data.access_level === "restricted" && (
              <div className="mt-4 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
                Restricted metadata.{" "}
                {reqState === "sent" ? (
                  <span className="font-medium">Access requested — the owning department will review it.</span>
                ) : isAuthenticated ? (
                  <button onClick={() => onRequest(query.data.fullyQualifiedName)} disabled={reqState === "sending"} className="font-medium underline disabled:opacity-60">
                    {reqState === "sending" ? "Requesting…" : "Request access"}
                  </button>
                ) : (
                  <Link to="/login" className="font-medium underline">
                    Sign in to request access
                  </Link>
                )}
                {reqState === "error" && <span className="ml-2 text-red-700">Could not send the request. Try again.</span>}
              </div>
            )}
          </div>

          <div className="mt-6 rounded-lg border border-slate-200 bg-white">
            <div className="border-b border-slate-200 px-4 py-3 text-sm font-semibold text-slate-900">
              Columns
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 text-left text-slate-500">
                  <tr>
                    <th scope="col" className="px-4 py-2 font-medium">Column Name</th>
                    <th scope="col" className="px-4 py-2 font-medium">Data Type</th>
                    <th scope="col" className="px-4 py-2 font-medium">Description</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {(query.data.columns ?? []).map((col) => (
                    <tr key={col.name}>
                      <td className="px-4 py-2 font-medium text-slate-900">{col.name}</td>
                      <td className="px-4 py-2">
                        <span className="rounded bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700">
                          {col.dataTypeDisplay || col.dataType || "-"}
                        </span>
                      </td>
                      <td className="px-4 py-2 text-slate-600">{col.description || "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
