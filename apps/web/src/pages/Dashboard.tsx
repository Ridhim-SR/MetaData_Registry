import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { getMetadataStats, health, listMetadataTables } from "../api/openmetadata";
import { useAuth } from "../contexts/AuthContext";

const statCards = [
  { key: "services", label: "Services" },
  { key: "databases", label: "Databases" },
  { key: "schemas", label: "Schemas" },
  { key: "tables", label: "Tables" },
  { key: "columns", label: "Columns" },
] as const;

export function DashboardPage() {
  const { user } = useAuth();

  const { isPending: omPending, isError: omError } = useQuery({
    queryKey: ["om-health"],
    queryFn: health,
    refetchInterval: 30_000,
  });

  const statsQuery = useQuery({
    queryKey: ["metadata-stats"],
    queryFn: getMetadataStats,
  });

  const tablesQuery = useQuery({
    queryKey: ["metadata-recent"],
    queryFn: () => listMetadataTables(),
  });

  const recent = (tablesQuery.data ?? []).slice(0, 6);

  return (
    <div>
      <h1 className="mb-6 text-2xl font-semibold">Dashboard</h1>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-6">
        {statCards.map((card) => (
          <div key={card.key} className="rounded-lg border border-slate-200 p-4">
            <div className="text-sm text-slate-500">{card.label}</div>
            <div className="mt-1 text-2xl font-semibold">
              {statsQuery.isPending ? "…" : (statsQuery.data?.[card.key] ?? 0)}
            </div>
          </div>
        ))}
        <div className="rounded-lg border border-slate-200 p-4">
          <div className="text-sm text-slate-500">OpenMetadata</div>
          <div className="mt-1 text-lg font-medium">
            {omPending ? "Checking…" : omError ? "Unreachable" : "Healthy"}
          </div>
          {omError && <div className="text-sm text-red-600">Verify OPENMETADATA_HOST</div>}
        </div>
      </div>

      <div className="mt-8">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-semibold">Recent datasets</h2>
          <Link to="/explore" className="text-sm font-medium text-slate-900 underline">
            Explore all
          </Link>
        </div>
        {tablesQuery.isPending && <p className="text-slate-500">Loading…</p>}
        {!tablesQuery.isPending && recent.length === 0 && (
          <p className="text-slate-500">
            No datasets yet.{" "}
            <Link to="/ingestion" className="text-slate-900 underline">
              Ingest a CSV
            </Link>{" "}
            to get started.
          </p>
        )}
        <div className="overflow-hidden rounded-lg border border-slate-200">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-slate-500">
              <tr>
                <th className="px-4 py-2 font-medium">Name</th>
                <th className="px-4 py-2 font-medium">Path</th>
                <th className="px-4 py-2 font-medium">Columns</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {recent.map((t) => {
                const parts = (t.fullyQualifiedName ?? "").split(".");
                return (
                  <tr key={t.id} className="hover:bg-slate-50">
                    <td className="px-4 py-2">
                      <Link to={`/explore/${t.id}`} className="font-medium text-slate-900 underline">
                        {t.name}
                      </Link>
                    </td>
                    <td className="px-4 py-2 text-slate-500">{parts.slice(0, -1).join(" / ")}</td>
                    <td className="px-4 py-2 text-slate-500">{t.columns?.length ?? 0}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      <div className="mt-8 rounded-lg border border-slate-200 p-4">
        <div className="text-sm text-slate-500">Signed in as</div>
        <div className="mt-1 text-lg font-medium">
          {user?.username} · <span className="capitalize">{user?.role}</span>
        </div>
        <div className="text-sm text-slate-500">{user?.email}</div>
      </div>
    </div>
  );
}
