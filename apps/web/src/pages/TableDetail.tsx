import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { getMetadataTable, type MetadataTable } from "../api/openmetadata";
import { ApiError } from "../api/client";

function crumbParts(table: MetadataTable) {
  return (table.fullyQualifiedName ?? "").split(".");
}

export function TableDetailPage() {
  const { tableId } = useParams<{ tableId: string }>();

  const query = useQuery({
    queryKey: ["metadata-table", tableId],
    queryFn: () => getMetadataTable(tableId!),
    enabled: Boolean(tableId),
  });

  if (query.isPending) return <p className="text-slate-500">Loading…</p>;

  if (query.error) {
    const detail = query.error instanceof ApiError ? query.error.detail : query.error.message;
    return (
      <div>
        <p className="mb-4 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{detail}</p>
        <Link to="/explore" className="text-sm font-medium text-slate-900 underline">
          ← Back to explore
        </Link>
      </div>
    );
  }

  const table = query.data;
  const crumbs = crumbParts(table);

  return (
    <div>
      <Link to="/explore" className="mb-4 inline-block text-sm font-medium text-slate-900 underline">
        ← Back to explore
      </Link>

      <div className="rounded-lg border border-slate-200 p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-sm text-slate-500">{crumbs.slice(0, -1).join(" / ")}</div>
            <h1 className="mt-1 text-2xl font-semibold text-slate-900">{table.name}</h1>
          </div>
          <div className="flex gap-4 text-sm text-slate-500">
            <span className="rounded-md bg-slate-100 px-3 py-1.5">{table.columns?.length ?? 0} columns</span>
            {table.service?.name && (
              <span className="rounded-md bg-slate-100 px-3 py-1.5">{table.service.name}</span>
            )}
          </div>
        </div>
        <p className="mt-4 text-sm text-slate-600">{table.description || "No description"}</p>
      </div>

      <div className="mt-6 rounded-lg border border-slate-200">
        <div className="border-b border-slate-200 px-4 py-3 text-sm font-semibold text-slate-900">
          Columns
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-slate-500">
              <tr>
                <th className="px-4 py-2 font-medium">Name</th>
                <th className="px-4 py-2 font-medium">Data type</th>
                <th className="px-4 py-2 font-medium">Description</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {(table.columns ?? []).map((col) => (
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
  );
}
