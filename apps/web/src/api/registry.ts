import { apiGet, apiGetText, apiPost } from "./client";

export type AccessLevel = "public" | "department" | "restricted" | "confidential";

export interface RegistryStats {
  departments: number;
  datasets: number;
  tables: number;
}

export interface Department {
  slug: string;
  /** Legacy alias for slug (raw service name); prefer slug. */
  name: string;
  display_name: string;
  short_name?: string | null;
  description?: string | null;
  aliases?: string[];
  contact_email?: string | null;
  contact_phone?: string | null;
  head_name?: string | null;
  category?: string | null;
  dataset_count: number;
  table_count: number;
}

export interface DepartmentDetail {
  profile: Department;
  datasets: DatasetCard[];
  total: number;
}

export interface RegistryOwner {
  id?: string;
  name?: string;
  displayName?: string;
  fullyQualifiedName?: string;
}

export interface RegistryTag {
  tagFQN?: string;
  name?: string;
  labelType?: string;
}

export interface TableInfo {
  api_available?: boolean | null;
  /** URL of the API documentation, when the backend exposes one. */
  api_docs_url?: string | null;
  dataset_owner?: string | null;
  frequency?: string | null;
  timeline?: string | null;
}

export interface RegistryTable {
  id: string;
  name: string;
  fullyQualifiedName: string;
  description?: string | null;
  columns?: Array<{ name: string; dataType?: string; dataTypeDisplay?: string; description?: string | null; tags?: RegistryTag[] }>;
  access_level?: AccessLevel;
  department?: string | null;
  department_display?: string | null;
  restricted?: boolean;
  locked?: boolean;
  column_count?: number;
  owners?: RegistryOwner[];
  tags?: RegistryTag[];
  /** Table-level data classification when the backend provides one. */
  data_classification?: string | null;
  info?: TableInfo | null;
  facts?: TableFacts | null;
}

export interface TableFacts {
  owner?: string | null;
  steward?: string | null;
  department_contact?: string | null;
  updated_at?: number | null;
  frequency?: string | null;
  source?: string | null;
}

export interface DatasetCard {
  /** Dataset identity: OM database FQN (service.database). */
  dataset: string;
  name: string;
  service: string;
  database: string;
  description?: string | null;
  table_count: number;
  access_level: AccessLevel;
  department?: string | null;
  department_display?: string | null;
  /** Teaser cards carry locked:true and no tables. Full cards carry tables. */
  locked: boolean;
  tables?: RegistryTable[];
  /** Distinct tagFQNs across visible member tables (empty for teasers). */
  tags?: string[];
  /** Max member-table updatedAt (epoch ms), null when unknown/hidden. */
  updated_at?: number | null;
}

export interface DatasetList {
  items: DatasetCard[];
  teasers?: RegistryTable[];
  total: number;
}

export interface SearchGroup<T> {
  items: T[];
  total: number;
}

export interface DepartmentHit extends Department {
  dataset_count: number;
  table_count: number;
}

export interface TableHit {
  id?: string;
  name?: string;
  fullyQualifiedName?: string;
  description?: string | null;
  department?: string | null;
  department_display?: string | null;
  dataset?: string;
  matched_in?: string[];
  matched_columns?: string[];
  tags?: string[];
  updated_at?: number | null;
  /** Table-level data classification when the search API provides one. */
  data_classification?: string | null;
}

export interface ColumnHit {
  name?: string;
  dataType?: string;
  table?: string;
  dataset?: string;
}

export interface SearchResult {
  departments: SearchGroup<DepartmentHit>;
  datasets: SearchGroup<DatasetCard>;
  tables: SearchGroup<TableHit>;
  columns: SearchGroup<ColumnHit>;
  /** Back-compat flat dataset list. */
  data: DatasetCard[];
  teasers?: RegistryTable[];
  total: number;
  page: number;
  fallback?: boolean;
}

export type SearchScope = "departments" | "datasets" | "tables" | "columns";

export function getRegistryStats() {
  return apiGet<RegistryStats>("/registry/stats");
}

export function listDepartments() {
  return apiGet<{ items: Department[]; total: number }>("/registry/departments");
}

export function getDepartment(slug: string) {
  return apiGet<DepartmentDetail>(`/registry/departments/${encodeURIComponent(slug)}`);
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

export function downloadTableDictionary(tableId: string) {
  return apiGetText(`/registry/tables/${encodeURIComponent(tableId)}/dictionary`);
}

export interface TableLineage {
  nodes?: Array<{ id?: string; name?: string; fullyQualifiedName?: string; type?: string }>;
  edges?: Array<{
    fromEntity?: { id?: string; name?: string; fullyQualifiedName?: string };
    toEntity?: { id?: string; name?: string; fullyQualifiedName?: string };
  }>;
  detail?: string;
}

export function getTableLineage(tableId: string) {
  return apiGet<TableLineage>(`/openmetadata/metadata/tables/${encodeURIComponent(tableId)}/lineage`);
}

export function searchRegistry(params: {
  q: string;
  department?: string;
  scope?: string;
  page?: number;
  size?: number;
}) {
  const qs = new URLSearchParams({ q: params.q });
  if (params.department) qs.set("department", params.department);
  if (params.scope) qs.set("scope", params.scope);
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
