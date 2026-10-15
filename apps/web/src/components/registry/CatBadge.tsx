import { catAccessNote, catLabel, classificationBadgeClass, normalizeClassification } from "../../utils/format";

/** Dataset CAT classification badge ("Open Access", never the CAT code); renders nothing when unclassified. */
export function CatBadge({ value }: { value: string | null | undefined }) {
  const label = catLabel(value);
  const level = normalizeClassification(value);
  if (!label || !level) return null;
  return (
    <span className={`badge ${classificationBadgeClass(level)}`} title={catAccessNote(value) ?? undefined}>
      {label}
    </span>
  );
}
