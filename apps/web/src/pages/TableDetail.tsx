import { useEffect } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getRegistryTable } from "../api/registry";
import { ApiError } from "../api/client";
import { EmptyBlock, LoadingBlock } from "../components/registry/StateBlocks";

/** Legacy table links resolve to their parent dataset (database-level). */
export function TableDetailPage() {
  const { tableId = "" } = useParams<{ tableId: string }>();
  const navigate = useNavigate();

  const query = useQuery({
    queryKey: ["registry-table", tableId],
    queryFn: () => getRegistryTable(tableId),
    enabled: Boolean(tableId),
    retry: false,
  });

  useEffect(() => {
    if (query.data?.fullyQualifiedName) {
      const parts = query.data.fullyQualifiedName.split(".");
      if (parts.length >= 2) {
        navigate(`/datasets/${encodeURIComponent(`${parts[0]}.${parts[1]}`)}`, { replace: true });
      }
    }
  }, [query.data, navigate]);

  return (
    <div className="mx-auto w-full max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      <Link to="/explore" className="mb-4 inline-block text-sm font-medium" style={{ color: "var(--blue-700)" }}>
        ← Back to catalog
      </Link>
      {query.isPending && <LoadingBlock lines={3} />}
      {query.error && query.error instanceof ApiError && query.error.status === 401 && (
        <EmptyBlock
          title="This metadata requires department access."
          body="Sign in with your department account to view it."
          action={
            <Link to="/login" className="btn-primary" style={{ fontSize: "0.875rem" }}>
              Sign In
            </Link>
          }
        />
      )}
      {query.error && !(query.error instanceof ApiError && query.error.status === 401) && (
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
    </div>
  );
}
