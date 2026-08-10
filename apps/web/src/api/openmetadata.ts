import { apiGet, apiPost, apiUpload } from "./client";

export interface PipelineTriggerResponse {
  status: string;
  pipeline_id: string;
  detail?: Record<string, unknown> | null;
}

export interface PostgresIngestionConfig {
  host: string;
  port: number;
  database: string;
  username: string;
  password: string;
  include_tables?: string[];
  exclude_tables?: string[];
}

export interface CsvIngestionConfig {
  file_path: string;
  table_name: string;
  delimiter: string;
  has_header: boolean;
  columns?: Record<string, string>[];
}

export interface IngestionPipelineDef {
  name: string;
  pipelineType?: string;
  sourceConfig?: Record<string, unknown>;
  sinkConfig?: Record<string, unknown>;
  serviceId?: string;
}

export function triggerPostgres(config: PostgresIngestionConfig) {
  return apiPost<PipelineTriggerResponse>("/openmetadata/ingestion/postgres", config);
}

export function triggerCsv(config: CsvIngestionConfig) {
  return apiPost<PipelineTriggerResponse>("/openmetadata/ingestion/csv", config);
}

export interface CsvUploadResponse {
  file_path: string;
  filename: string;
  size: number;
}

export function uploadCsv(file: File) {
  return apiUpload<CsvUploadResponse>("/openmetadata/ingestion/csv/upload", file);
}

export function listPipelines(): Promise<Array<Record<string, unknown>>> {
  return apiGet<Array<Record<string, unknown>>>("/openmetadata/ingestion/pipelines");
}

export function createPipeline(pipeline: IngestionPipelineDef) {
  return apiPost("/openmetadata/ingestion/pipelines", pipeline);
}

export function triggerPipeline(pipelineId: string) {
  return apiPost<PipelineTriggerResponse>("/openmetadata/ingestion/pipelines/trigger", { pipeline_id: pipelineId });
}

export function health() {
  return apiGet<Record<string, unknown>>("/openmetadata/ingestion/health");
}

export interface MetadataColumn {
  name: string;
  dataType?: string;
  dataTypeDisplay?: string;
  description?: string | null;
}

export interface MetadataTable {
  id: string;
  name: string;
  fullyQualifiedName: string;
  description?: string | null;
  columns?: MetadataColumn[];
  service?: { name: string } | null;
  database?: { name: string } | null;
  databaseSchema?: { name: string } | null;
}

export interface MetadataStats {
  services: number;
  databases: number;
  schemas: number;
  tables: number;
  columns: number;
}

export interface MetadataFilters {
  search?: string;
  service?: string;
  database?: string;
  schema?: string;
}

export function listMetadataTables(filters: MetadataFilters = {}) {
  const qs = new URLSearchParams();
  if (filters.search) qs.set("search", filters.search);
  if (filters.service) qs.set("service", filters.service);
  if (filters.database) qs.set("database", filters.database);
  if (filters.schema) qs.set("schema", filters.schema);
  const suffix = qs.toString();
  return apiGet<MetadataTable[]>(`/openmetadata/metadata/tables${suffix ? `?${suffix}` : ""}`);
}

export function getMetadataTable(tableId: string) {
  return apiGet<MetadataTable>(`/openmetadata/metadata/tables/${encodeURIComponent(tableId)}`);
}

export function getMetadataStats() {
  return apiGet<MetadataStats>("/openmetadata/metadata/stats");
}
