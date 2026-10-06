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
