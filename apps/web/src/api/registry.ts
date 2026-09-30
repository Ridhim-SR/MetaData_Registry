import { apiGet, apiPost } from "./client";

export type AccessLevel = "public" | "department" | "restricted";

export interface RegistryStats {
  departments: number;
  datasets: number;
  tables: number;
  public_tables: number;
}

export interface Department {
  name: string;
  description?: string | null;
  dataset_count: number;
  table_count: number;
}

export interface RegistryTable {
  id: string;
  name: string;
  fullyQualifiedName: string;
  description?: string | null;
  columns?: Array<{ name: string; dataType?: string; dataTypeDisplay?: string; description?: string | null }>;
  access_level?: AccessLevel;
  department?: string | null;
  restricted?: boolean;
}

export interface DatasetCard {
  dataset: string;
  name: string;
  service: string;
  database: string;
  schema: string;
  table_count: number;
  access_level: AccessLevel;
  department?: string | null;
  tables: RegistryTable[];
}

export interface DatasetList {
  items: DatasetCard[];
  teasers?: RegistryTable[];
  total: number;
}

export interface SearchResult {
  data: RegistryTable[];
  teasers?: RegistryTable[];
  total: number;
  page: number;
  fallback?: boolean;
}

export function getRegistryStats() {
  return apiGet<RegistryStats>("/registry/stats");
}

export function listDepartments() {
  return apiGet<{ items: Department[]; total: number }>("/registry/departments");
}

export function listPublicDatasets() {
  return apiGet<DatasetList>("/registry/datasets/public");
}

export function listDatasets(params: { department?: string; search?: string } = {}) {
  const qs = new URLSearchParams();
  if (params.department) qs.set("department", params.department);
  if (params.search) qs.set("search", params.search);
  const suffix = qs.toString();
  return apiGet<DatasetList>(`/registry/datasets${suffix ? `?${suffix}` : ""}`);
}

export function getDataset(fqn: string) {
  return apiGet<DatasetCard>(`/registry/datasets/by-fqn?fqn=${encodeURIComponent(fqn)}`);
}

export function getRegistryTable(tableId: string) {
  return apiGet<RegistryTable>(`/registry/tables/${encodeURIComponent(tableId)}`);
}

export function searchRegistry(params: { q: string; department?: string; page?: number; size?: number }) {
  const qs = new URLSearchParams({ q: params.q });
  if (params.department) qs.set("department", params.department);
  if (params.page) qs.set("page", String(params.page));
  if (params.size) qs.set("size", String(params.size));
  return apiGet<SearchResult>(`/registry/search?${qs.toString()}`);
}

export function requestAccess(fqn: string, note?: string) {
  return apiPost<{ id: number; fqn: string; status: string }>("/registry/access-requests", {
    fqn,
    note,
  });
}

export function getDepartmentSummary(department: string) {
  return apiGet<{
    department: string;
    tables: number;
    columns: number;
    topSchemas: Array<{ schema: string; tables: number }>;
    recent: Array<{ id: string; name: string; fullyQualifiedName: string }>;
  }>(`/openmetadata/metadata/departments/${encodeURIComponent(department)}/summary`);
}
