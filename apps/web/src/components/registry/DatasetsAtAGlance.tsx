import { useQuery } from "@tanstack/react-query";
import { getRegistryStats } from "../../api/registry";
import { formatNumber, t, useLanguage } from "../../i18n";
import type { I18nKey } from "../../i18n";
import { CAT_CATEGORIES } from "../../utils/format";
import { Skeleton } from "./StateBlocks";

// Bar colours follow the CAT badge colours (badge-public .. badge-confidential).
const CAT_COLORS: Record<number, string> = {
  1: "var(--public-fg)",
  2: "var(--dept-fg)",
  3: "var(--restricted-fg)",
  4: "var(--confid-fg)",
};

// `key` is the API value in by_dataset_type; label/detail are display strings.
const DATASET_TYPES: Array<{ key: string; label: I18nKey; detail: I18nKey; color: string }> = [
  { key: "Citizen Centric", label: "typeCitizenCentric", detail: "typeCitizenCentricDetail", color: "var(--blue-700)" },
  { key: "Administrative", label: "typeAdministrative", detail: "typeAdministrativeDetail", color: "var(--navy-900)" },
];

type Row = { key: string; label: string; detail: string | null; count: number; color: string };

/**
 * "Datasets at a glance" — dataset counts by classification and by dataset
 * type, from the same /registry/stats response (and query cache) as the
 * StatsBar above, so each chart always adds up to its Datasets total.
 * CAT-1..CAT-3 and both dataset types are always shown; CAT-4 (admins
 * only), "Not classified" and "Not specified" only when they have datasets.
 */
export function DatasetsAtAGlance() {
  useLanguage();
  const query = useQuery({ queryKey: ["registry-stats"], queryFn: getRegistryStats });
  const loading = query.isPending || query.isFetching;
  const byCat = query.data?.by_classification;
  const byType = query.data?.by_dataset_type;

  const catRows: Row[] = CAT_CATEGORIES.map((c) => ({
    key: `CAT-${c.level}`,
    label: `CAT-${c.level}`,
    detail: c.name,
    count: byCat?.[`CAT-${c.level}`] ?? 0,
    color: CAT_COLORS[c.level],
  })).filter((r) => r.key !== "CAT-4" || r.count > 0);
  if ((byCat?.unclassified ?? 0) > 0) {
    catRows.push({ key: "unclassified", label: t("notClassified"), detail: null, count: byCat!.unclassified, color: "var(--text-muted)" });
  }

  const typeRows: Row[] = DATASET_TYPES.map((d) => ({
    key: d.key,
    label: t(d.label),
    detail: t(d.detail),
    count: byType?.[d.key] ?? 0,
    color: d.color,
  }));
  if ((byType?.unspecified ?? 0) > 0) {
    typeRows.push({ key: "unspecified", label: t("notSpecified"), detail: null, count: byType!.unspecified, color: "var(--text-muted)" });
  }

  // The StatsBar already reports load errors; an empty catalog needs no chart.
  if (!loading && (query.error || !byCat || query.data?.datasets === 0)) return null;

  return (
    <section aria-label={t("glanceTitle")} style={{ background: "var(--bg)" }}>
      <div className="page-container mx-auto w-full max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
        <h2 className="font-semibold" style={{ color: "var(--navy-900)", fontSize: "1.375rem" }}>
          {t("glanceTitle")}
        </h2>
        <p className="mt-1 text-sm" style={{ color: "var(--text-muted)", fontSize: "0.9375rem" }}>
          {t("glanceSubtitle")}
        </p>

        {/* Exactly two cards, so split the row in half (stacked on small screens). */}
        <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
          {loading ? (
            <>
              <Skeleton className="h-44" />
              <Skeleton className="h-44" />
            </>
          ) : (
            <>
              <BarCard title={t("byClassification")} rows={catRows} />
              {/* Older APIs don't send by_dataset_type yet; show the chart once they do. */}
              {byType && <BarCard title={t("byDatasetType")} rows={typeRows} />}
            </>
          )}
        </div>
      </div>
    </section>
  );
}

function BarCard({ title, rows }: { title: string; rows: Row[] }) {
  const max = Math.max(1, ...rows.map((r) => r.count));
  return (
    <div className="p-5" style={{ border: "1px solid var(--border)", borderRadius: 6, background: "var(--bg)" }}>
      <h3 className="font-semibold" style={{ color: "var(--navy-900)", fontSize: "1rem" }}>
        {title}
      </h3>
      <ul className="mt-3" style={{ display: "grid", gap: "12px" }}>
        {rows.map((r) => (
          <li key={r.key}>
            <div className="flex items-baseline justify-between gap-3" style={{ fontSize: "0.875rem" }}>
              <span>
                <span className="font-semibold" style={{ color: "var(--navy-900)" }}>
                  {r.label}
                </span>
                {r.detail && <span style={{ color: "var(--text-muted)" }}> · {r.detail}</span>}
              </span>
              <span className="font-semibold" style={{ color: "var(--navy-900)" }}>
                {formatNumber(r.count)}
                <span className="sr-only"> {t(r.count === 1 ? "datasetWordOne" : "datasetWordOther")}</span>
              </span>
            </div>
            <div
              aria-hidden="true"
              className="mt-1"
              style={{ height: 8, borderRadius: 4, background: "var(--bg-alt)", overflow: "hidden" }}
            >
              <div style={{ width: `${(r.count / max) * 100}%`, height: "100%", background: r.color, borderRadius: 4 }} />
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
