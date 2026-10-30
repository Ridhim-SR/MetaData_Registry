import { apiGet, apiGetText, apiPost } from "./client";

export type AccessLevel = "public" | "department" | "restricted" | "confidential";

export interface RegistryStats {
  departments: number;
  datasets: number;
  tables: number;
  /** Visible datasets per CAT category ("CAT-1".."CAT-4", "unclassified"); sums to `datasets`. */
  by_classification?: Record<string, number>;
  /** Visible datasets per type ("Citizen Centric", "Administrative", "unspecified"); sums to `datasets`. */
  by_dataset_type?: Record<string, number>;
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

/** Raw table sidecar row: API flag plus per-table overrides (may be empty). */
export interface TableInfo {
  api_available?: boolean | null;
  /** URL of the API documentation, when the backend exposes one. */
  api_docs_url?: string | null;
  /** Per-table owner override; empty means the dataset owner applies. */
  dataset_owner?: string | null;
  frequency?: string | null;
  timeline?: string | null;
}

/** Where a resolved fact came from: the table itself or its parent dataset. */
export type FactOrigin = "table" | "dataset" | null;

export interface RegistryTable {
  id: string;
  name: string;
  fullyQualifiedName: string;
  description?: string | null;
  columns?: Array<{ name: string; displayName?: string | null; dataType?: string; dataTypeDisplay?: string; description?: string | null; tags?: RegistryTag[] }>;
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

/** Table facts with dataset inheritance already applied by the backend. */
export interface TableFacts {
  owner?: string | null;
  steward?: string | null;
  department_contact?: string | null;
  updated_at?: number | null;
  frequency?: string | null;
  timeline?: string | null;
  api_available?: boolean | null;
  data_classification?: string | null;
  /** Description of the classification tag (e.g. what CAT-3 means). */
  data_classification_description?: string | null;
  source?: string | null;
  origin?: {
    owner?: FactOrigin;
    steward?: FactOrigin;
    frequency?: FactOrigin;
    timeline?: FactOrigin;
    api_available?: FactOrigin;
    data_classification?: FactOrigin;
  };
}

/** Dataset-level defaults plus summaries over the viewer's visible tables. */
export interface DatasetInfo {
  owner?: string | null;
  steward?: string | null;
  frequency?: string | null;
  timeline?: string | null;
  /** Dataset-level API flag (OM apiAvailable custom property). */
  api_available?: boolean | null;
  /** Tables marked as exposed via an API. */
  api_tables: number;
  /** Tables with a known (yes/no) API flag. */
  api_known: number;
  table_count: number;
  /** Dataset classification tag, else the most restrictive among its tables. */
  data_classification?: string | null;
  data_classification_description?: string | null;
  /** Where the schema came from: "Department Provided" or "Public Extraction" (OM schemaSource). */
  schema_source?: string | null;
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
  /** Dataset CAT category ("CAT-1".."CAT-4") from OM DataSensitivity tags; drives access. */
  classification?: string | null;
  /** "Citizen Centric" | "Administrative" from the OM datasetType custom property; null when not set. */
  dataset_type?: string | null;
  department?: string | null;
  department_display?: string | null;
  /** Teaser cards carry locked:true and no tables. Full cards carry tables. */
  locked: boolean;
  tables?: RegistryTable[];
  /** Distinct tagFQNs across visible member tables (empty for teasers). */
  tags?: string[];
  /** Max member-table updatedAt (epoch ms), null when unknown/hidden. */
  updated_at?: number | null;
  /** Dataset-level facts; only on unlocked cards (list and getDataset). */
  info?: DatasetInfo | null;
}

export interface FacetOption {
  value: string;
  count: number;
  /** Display name (departments only). */
  label?: string;
}

/** Filter option counts from the API; each ignores its own selection. */
export interface CatalogFacets {
  classification: FacetOption[];
  tags: FacetOption[];
  department: FacetOption[];
  frequency: FacetOption[];
  /** "yes" / "no". */
  api: FacetOption[];
  steward: FacetOption[];
  /** "Department Provided" / "Public Extraction"; absent from older APIs. */
  schema_source?: FacetOption[];
  /** Overall timeline span, null when no dataset has a timeline. */
  years: { min: number; max: number } | null;
}

/** Catalog filters: values ORed within a filter, filters ANDed. */
export interface CatalogFilterParams {
  department?: string | string[];
  classification?: string[];
  tag?: string[];
  frequency?: string[];
  api?: string[];
  steward?: string[];
  schema_source?: string[];
  year_from?: number | null;
  year_to?: number | null;
  sort?: "relevance" | "updated" | "name";
  page?: number;
  size?: number;
}

export interface DatasetList {
  items: DatasetCard[];
  teasers?: RegistryTable[];
  /** Filtered count (all pages). */
  total: number;
  department_count?: number;
  page?: number;
  size?: number;
  facets?: CatalogFacets;
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
  department_count?: number;
  page: number;
  size?: number;
  facets?: CatalogFacets;
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

/** Append filters to a query string (repeated keys for several values). */
function appendFilters(qs: URLSearchParams, params: CatalogFilterParams) {
  const lists: Array<[string, string | string[] | undefined]> = [
    ["department", params.department],
    ["classification", params.classification],
    ["tag", params.tag],
    ["frequency", params.frequency],
    ["api", params.api],
    ["steward", params.steward],
    ["schema_source", params.schema_source],
  ];
  for (const [key, value] of lists) {
    for (const v of Array.isArray(value) ? value : value ? [value] : []) qs.append(key, v);
  }
  if (params.year_from != null) qs.set("year_from", String(params.year_from));
  if (params.year_to != null) qs.set("year_to", String(params.year_to));
  if (params.sort && params.sort !== "relevance") qs.set("sort", params.sort);
  if (params.page) qs.set("page", String(params.page));
  if (params.size) qs.set("size", String(params.size));
}

export function listDatasets(params: CatalogFilterParams & { search?: string } = {}) {
  const qs = new URLSearchParams();
  appendFilters(qs, params);
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

export function searchRegistry(params: CatalogFilterParams & { q: string; scope?: string }) {
  const qs = new URLSearchParams({ q: params.q });
  appendFilters(qs, params);
  if (params.scope) qs.set("scope", params.scope);
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
