/** Display helper: show DB values with a capital first letter.
 * Data stays untouched (links, FQNs, API params still use raw values);
 * only rendered labels go through this.
 */
export function capitalizeFirst(value: string | null | undefined): string {
  if (!value) return "";
  return value.charAt(0).toUpperCase() + value.slice(1);
}

/**
 * Display-only fallback for OM names without a proper displayName.
 * Data engineering owns display names in OM; until they are set, raw IDs
 * like "public_works_department" would leak into the UI. This prettifies
 * ONLY strings that look like raw IDs (contain _ or -); proper display
 * names ("Crop Statistics", "Vishwakarma GIS Data") pass through untouched.
 * Links, FQNs and API params always keep the raw value.
 */
export function humanizeRaw(value: string | null | undefined): string {
  if (!value) return "Not provided";
  if (!/[_-]/.test(value)) return value;
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .split(" ")
    .map((w) => (w ? w.charAt(0).toUpperCase() + w.slice(1).toLowerCase() : w))
    .join(" ");
}

/** "Not provided" placeholder for missing metadata — never render blank. */
export function orNotProvided(value: string | null | undefined): string {
  const v = (value ?? "").trim();
  return v ? v : "Not provided";
}

/** True when an `updated_at` value is a usable epoch-ms timestamp. */
export function hasValidUpdatedAt(value: number | null | undefined): value is number {
  return typeof value === "number" && Number.isFinite(value) && value > 0;
}

/** en-IN short date for epoch-ms timestamps; null when missing or invalid. */
export function formatUpdatedAt(value: number | null | undefined): string | null {
  if (!hasValidUpdatedAt(value)) return null;
  try {
    return new Date(value).toLocaleDateString("en-IN", {
      day: "2-digit",
      month: "short",
      year: "numeric",
    });
  } catch {
    return null;
  }
}

/**
 * Readable tag label from OM tag objects (tagFQN / displayName / name).
 * "MDSF.Internal" -> "Internal", "FieldTag.Date/Timestamp" -> "Date/Timestamp".
 * Proper display names pass through untouched.
 */
export function readableTag(tag: { tagFQN?: string; displayName?: string; name?: string } | null | undefined): string {
  if (!tag) return "Not provided";
  const raw = tag.displayName || tag.tagFQN || tag.name || "";
  if (!raw) return "Not provided";
  const afterDot = raw.includes(".") ? raw.slice(raw.lastIndexOf(".") + 1) : raw;
  return afterDot || raw;
}

/** Data-classification levels, lowest to highest sensitivity. */
export type DataClassification = "Public" | "Internal" | "Restricted" | "Sensitive";

/**
 * Normalize an explicit classification value from the backend to a level.
 * Only a real backend/OM-provided value counts — tags are never guessed
 * from here, so unknown or missing values return null ("Not provided").
 */
export function normalizeClassification(value: string | null | undefined): DataClassification | null {
  const v = (value ?? "").trim().toLowerCase();
  if (!v) return null;
  if (v === "public" || v === "open") return "Public";
  if (v === "internal") return "Internal";
  if (v === "restricted") return "Restricted";
  if (v === "sensitive" || v === "pii" || v === "confidential" || v === "secret" || v === "personal") {
    return "Sensitive";
  }
  return null;
}

const SENSITIVE_TAG_PATTERN = /(pii|personal|sensitive|confidential|restricted|secret)/i;

/** True when a tag marks personal/sensitive data (drives the sensitivity summary). */
export function isSensitiveTag(tag: { tagFQN?: string; displayName?: string; name?: string } | null | undefined): boolean {
  if (!tag) return false;
  return SENSITIVE_TAG_PATTERN.test(`${tag.tagFQN ?? ""} ${tag.displayName ?? ""} ${tag.name ?? ""}`);
}

/**
 * Metadata-completeness estimate (0-100) for a dataset card, derived only from
 * already-fetched fields: tables having a description and at least one column.
 * No backend change required.
 */
export function completenessPct(
  tables: Array<{ description?: string | null; columns?: unknown[] | null }>,
): number {
  if (!tables || tables.length === 0) return 0;
  let points = 0;
  for (const t of tables) {
    if (t.description && String(t.description).trim()) points += 1;
    if (Array.isArray(t.columns) && t.columns.length > 0) points += 1;
  }
  return Math.round((points / (tables.length * 2)) * 100);
}
