import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { listMetadataTables, type MetadataTable } from "../api/openmetadata";
import { ApiError } from "../api/client";

function fqnPath(table: MetadataTable): string {
  return (table.fullyQualifiedName ?? "").split(".").slice(0, -1).join(" / ");
}

export function ExplorePage() {
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [service, setService] = useState("");
  const [database, setDatabase] = useState("");
  const [schema, setSchema] = useState("");

  const allTables = useQuery({
    queryKey: ["metadata-facets"],
    queryFn: () => listMetadataTables(),
  });

  const facets = useMemo(() => {
    const tables = allTables.data ?? [];
    const services = new Set<string>();
    const databases = new Set<string>();
    const schemas = new Set<string>();
    for (const t of tables) {
      const parts = (t.fullyQualifiedName ?? "").split(".");
      if (parts[0]) services.add(parts[0]);
      if (parts[1]) databases.add(parts[1]);
      if (parts[2]) schemas.add(parts[2]);
    }
    return {
      services: [...services].sort(),
      databases: [...databases].sort(),
      schemas: [...schemas].sort(),
    };
  }, [allTables.data]);

  const tablesQuery = useQuery({
    queryKey: ["metadata-tables", debouncedSearch, service, database, schema],
    queryFn: () =>
      listMetadataTables({
        search: debouncedSearch || undefined,
        service: service || undefined,
        database: database || undefined,
        schema: schema || undefined,
      }),
  });

  const error = tablesQuery.error instanceof ApiError ? tablesQuery.error.detail : null;

  return (
    <div>
      <h1 className="mb-6 text-2xl font-semibold">Explore datasets</h1>

      <div className="mb-4 flex flex-wrap gap-3">
        <input
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            window.setTimeout(() => setDebouncedSearch(e.target.value), 300);
          }}
          placeholder="Search tables, columns, descriptions…"
          className="min-w-64 flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none"
        />
        <select
          value={service}
          onChange={(e) => setService(e.target.value)}
          className="rounded-md border border-slate-300 px-3 py-2 text-sm"
        >
          <option value="">All services</option>
          {facets.services.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <select
          value={database}
          onChange={(e) => setDatabase(e.target.value)}
          className="rounded-md border border-slate-300 px-3 py-2 text-sm"
        >
          <option value="">All databases</option>
          {facets.databases.map((d) => (
            <option key={d} value={d}>
              {d}
            </option>
          ))}
        </select>
        <select
          value={schema}
          onChange={(e) => setSchema(e.target.value)}
          className="rounded-md border border-slate-300 px-3 py-2 text-sm"
        >
          <option value="">All schemas</option>
          {facets.schemas.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>

      {error && <div className="mb-4 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>}

      {tablesQuery.isPending && <p className="text-slate-500">Loading…</p>}

      {tablesQuery.data && tablesQuery.data.length === 0 && (
        <p className="text-slate-500">No datasets match. Try a different search or clear filters.</p>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {(tablesQuery.data ?? []).map((table) => (
          <Link
            key={table.id}
            to={`/explore/${table.id}`}
            className="rounded-lg border border-slate-200 p-4 transition-shadow hover:shadow-md"
          >
            <div className="text-sm text-slate-500">{fqnPath(table)}</div>
            <div className="mt-1 text-lg font-semibold text-slate-900">{table.name}</div>
            <div className="mt-1 line-clamp-2 text-sm text-slate-600">
              {table.description || "No description"}
            </div>
            <div className="mt-3 flex gap-4 text-xs text-slate-500">
              <span>{table.columns?.length ?? 0} columns</span>
              {table.service?.name && <span>{table.service.name}</span>}
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
