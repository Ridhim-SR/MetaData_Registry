import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import {
  createPipeline,
  listPipelines,
  triggerCsv,
  triggerPipeline,
  triggerPostgres,
  uploadCsv,
  type PostgresIngestionConfig,
  type CsvIngestionConfig,
} from "../api/openmetadata";
import { ApiError } from "../api/client";

const PG_DEFAULTS: PostgresIngestionConfig = {
  host: "localhost",
  port: 5432,
  database: "appdb",
  username: "postgres",
  password: "postgres",
};

function ErrorBox({ error }: { error: string | null }) {
  if (!error) return null;
  return <div className="mb-4 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>;
}

function ResultBox({ data }: { data: unknown }) {
  if (!data) return null;
  return (
    <pre className="mt-4 max-h-64 overflow-auto rounded-md bg-slate-900 px-3 py-2 text-xs text-green-300">
      {JSON.stringify(data, null, 2)}
    </pre>
  );
}

export function IngestionPage() {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<"postgres" | "csv" | "pipelines">("postgres");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<unknown>(null);

  // Postgres form
  const [pg, setPg] = useState<PostgresIngestionConfig>(PG_DEFAULTS);

  // CSV form
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [csv, setCsv] = useState<CsvIngestionConfig>({
    file_path: "",
    table_name: "csv_import",
    delimiter: ",",
    has_header: true,
  });

  const { data: pipelines, isPending: pipelinesPending } = useQuery({
    queryKey: ["om-pipelines"],
    queryFn: listPipelines,
    enabled: activeTab === "pipelines",
  });

  const pgMutation = useMutation({
    mutationFn: triggerPostgres,
    onSuccess: (data) => {
      setResult(data);
      setError(null);
    },
    onError: (err: Error) => setError(err instanceof ApiError ? err.detail : err.message),
  });

  const csvMutation = useMutation({
    mutationFn: triggerCsv,
    onSuccess: (data) => {
      setResult(data);
      setError(null);
    },
    onError: (err: Error) => setError(err instanceof ApiError ? err.detail : err.message),
  });

  const csvUploadMutation = useMutation({
    mutationFn: uploadCsv,
    onSuccess: (data) => {
      setCsv((prev) => ({ ...prev, file_path: data.file_path }));
      csvMutation.mutate({ ...csv, file_path: data.file_path });
    },
    onError: (err: Error) => setError(err instanceof ApiError ? err.detail : err.message),
  });

  const triggerMutation = useMutation({
    mutationFn: triggerPipeline,
    onSuccess: (data) => {
      setResult(data);
      setError(null);
    },
    onError: (err: Error) => setError(err instanceof ApiError ? err.detail : err.message),
  });

  const createMutation = useMutation({
    mutationFn: () =>
      createPipeline({ name: `demo_${Date.now()}`, pipelineType: "metadata" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["om-pipelines"] });
      setError(null);
    },
    onError: (err: Error) => setError(err instanceof ApiError ? err.detail : err.message),
  });

  const submitPg = (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setResult(null);
    pgMutation.mutate(pg);
  };

  const submitCsv = (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setResult(null);
    if (!csvFile) {
      setError("Please choose a CSV file first.");
      return;
    }
    csvUploadMutation.mutate(csvFile);
  };

  const tabCls = (tab: string) =>
    `rounded-t-md px-4 py-2 text-sm font-medium ${
      activeTab === tab ? "border-b-2 border-slate-900 bg-white" : "text-slate-500 hover:text-slate-800"
    }`;

  return (
    <div>
      <h1 className="mb-6 text-2xl font-semibold">OpenMetadata Ingestion</h1>

      <div className="mb-6 flex gap-4 border-b border-slate-200">
        <button className={tabCls("postgres")} onClick={() => setActiveTab("postgres")}>
          PostgreSQL
        </button>
        <button className={tabCls("csv")} onClick={() => setActiveTab("csv")}>
          CSV
        </button>
        <button className={tabCls("pipelines")} onClick={() => setActiveTab("pipelines")}>
          Pipelines
        </button>
      </div>

      {activeTab === "postgres" && (
        <form onSubmit={submitPg} className="max-w-md space-y-4">
          <ErrorBox error={error} />
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-700">Host</label>
              <input
                value={pg.host}
                onChange={(e) => setPg({ ...pg, host: e.target.value })}
                className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-700">Port</label>
              <input
                type="number"
                value={pg.port}
                onChange={(e) => setPg({ ...pg, port: Number(e.target.value) })}
                className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none"
              />
            </div>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Database</label>
            <input
              value={pg.database}
              onChange={(e) => setPg({ ...pg, database: e.target.value })}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none"
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-700">Username</label>
              <input
                value={pg.username}
                onChange={(e) => setPg({ ...pg, username: e.target.value })}
                className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-700">Password</label>
              <input
                type="password"
                value={pg.password}
                onChange={(e) => setPg({ ...pg, password: e.target.value })}
                className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none"
              />
            </div>
          </div>
          <button
            type="submit"
            disabled={pgMutation.isPending}
            className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
          >
            {pgMutation.isPending ? "Ingesting…" : "Run PostgreSQL ingestion"}
          </button>
          {result ? <ResultBox data={result} /> : null}
        </form>
      )}

      {activeTab === "csv" && (
        <form onSubmit={submitCsv} className="max-w-md space-y-4">
          <ErrorBox error={error} />
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">CSV file</label>
            <input
              type="file"
              accept=".csv,text/csv"
              onChange={(e) => setCsvFile(e.target.files?.[0] ?? null)}
              className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700 file:mr-3 file:rounded file:border-0 file:bg-slate-900 file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-white hover:file:bg-slate-700"
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-700">Table name</label>
              <input
                value={csv.table_name}
                onChange={(e) => setCsv({ ...csv, table_name: e.target.value })}
                className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-700">Delimiter</label>
              <input
                value={csv.delimiter}
                onChange={(e) => setCsv({ ...csv, delimiter: e.target.value })}
                maxLength={2}
                className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none"
              />
            </div>
          </div>
          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={csv.has_header}
              onChange={(e) => setCsv({ ...csv, has_header: e.target.checked })}
              className="h-4 w-4"
            />
            First row is a header
          </label>
          <button
            type="submit"
            disabled={csvUploadMutation.isPending || csvMutation.isPending}
            className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
          >
            {csvUploadMutation.isPending || csvMutation.isPending ? "Ingesting…" : "Upload & run CSV ingestion"}
          </button>
          {result ? <ResultBox data={result} /> : null}
        </form>
      )}

      {activeTab === "pipelines" && (
        <div className="max-w-2xl">
          <ErrorBox error={error} />
          <div className="mb-4 flex gap-3">
            <button
              onClick={() => createMutation.mutate()}
              disabled={createMutation.isPending}
              className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
            >
              Create demo pipeline
            </button>
            {result ? <ResultBox data={result} /> : null}
          </div>
          {pipelinesPending && <p className="text-slate-500">Loading…</p>}
          {pipelines && pipelines.length === 0 && <p className="text-slate-500">No pipelines yet.</p>}
          <div className="overflow-hidden rounded-lg border border-slate-200">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-left text-slate-500">
                <tr>
                  <th className="px-4 py-2 font-medium">Name</th>
                  <th className="px-4 py-2 font-medium">Type</th>
                  <th className="px-4 py-2 font-medium">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {pipelines?.map((p, i) => (
                  <tr key={String(p.id ?? i)}>
                    <td className="px-4 py-2 font-medium">{String(p.name ?? "-")}</td>
                    <td className="px-4 py-2">{String(p.pipelineType ?? "-")}</td>
                    <td className="px-4 py-2">
                      <button
                        onClick={() => triggerMutation.mutate(String(p.id ?? ""))}
                        disabled={triggerMutation.isPending}
                        className="rounded bg-slate-100 px-2 py-1 text-xs font-medium hover:bg-slate-200 disabled:opacity-50"
                      >
                        Trigger
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
