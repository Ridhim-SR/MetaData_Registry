import {
  CAT_CATEGORIES,
  catAccessNote,
  catLabel,
  classificationBadgeClass,
  normalizeClassification,
} from "../../utils/format";

/**
 * Dataset classification badge ("CAT-1") with an info icon whose tooltip
 * (hover or keyboard focus) explains all four categories, highlighting the
 * current one. Renders nothing when the dataset is unclassified.
 */
export function CatBadge({ value }: { value: string | null | undefined }) {
  const label = catLabel(value);
  const level = normalizeClassification(value);
  if (!label || !level) return null;
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: "0.3rem" }}>
      <span className={`badge ${classificationBadgeClass(level)}`} title={catAccessNote(value) ?? undefined}>
        {label}
      </span>
      <CatInfo current={label} />
    </span>
  );
}

function CatInfo({ current }: { current: string }) {
  return (
    <span tabIndex={0} aria-label="What do the data categories mean?" className="cat-info">
      <span aria-hidden="true">i</span>
      <span role="tooltip" className="cat-info-tip">
        <span className="cat-info-title">Data categories</span>
        {CAT_CATEGORIES.map((c) => {
          const code = `CAT-${c.level}`;
          return (
            <span key={code} className={`cat-info-row${code === current ? " cat-info-current" : ""}`}>
              <strong>
                {code} · {c.name}
              </strong>
              <span>
                {c.meaning} {c.access}
              </span>
            </span>
          );
        })}
      </span>
    </span>
  );
}
