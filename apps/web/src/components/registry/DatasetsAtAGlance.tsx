import { useQuery } from "@tanstack/react-query";
import { getRegistryStats } from "../../api/registry";
import { CAT_CATEGORIES } from "../../utils/format";
import { Skeleton } from "./StateBlocks";

// Bar colours follow the CAT badge colours (badge-public .. badge-confidential).
const CAT_COLORS: Record<number, string> = {
  1: "var(--public-fg)",
  2: "var(--dept-fg)",
  3: "var(--restricted-fg)",
  4: "var(--confid-fg)",
};

const DATASET_TYPES: Array<{ key: string; detail: string; color: string }> = [
  { key: "Citizen Centric", detail: "About citizens and beneficiaries", color: "var(--blue-700)" },
  { key: "Administrative", detail: "Schemes, budgets and works", color: "var(--navy-900)" },
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
    catRows.push({ key: "unclassified", label: "Not classified", detail: null, count: byCat!.unclassified, color: "var(--text-muted)" });
  }

  const typeRows: Row[] = DATASET_TYPES.map((t) => ({
    key: t.key,
    label: t.key,
    detail: t.detail,
    count: byType?.[t.key] ?? 0,
    color: t.color,
  }));
  if ((byType?.unspecified ?? 0) > 0) {
    typeRows.push({ key: "unspecified", label: "Not specified", detail: null, count: byType!.unspecified, color: "var(--text-muted)" });
  }

  // The StatsBar already reports load errors; an empty catalog needs no chart.
  if (!loading && (query.error || !byCat || query.data?.datasets === 0)) return null;

  return (
    <section aria-label="Datasets at a glance" style={{ background: "var(--bg)" }}>
      <div className="page-container mx-auto w-full max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
        <h2 className="font-semibold" style={{ color: "var(--navy-900)", fontSize: "1.375rem" }}>
          Datasets at a glance
        </h2>
        <p className="mt-1 text-sm" style={{ color: "var(--text-muted)", fontSize: "0.9375rem" }}>
          How the published datasets are classified, and who they are about.
        </p>

        <div
          className="mt-4"
          style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: "16px" }}
        >
          {loading ? (
            <>
              <Skeleton className="h-44" />
              <Skeleton className="h-44" />
            </>
          ) : (
            <>
              <BarCard title="By classification" rows={catRows} />
              {/* Older APIs don't send by_dataset_type yet; show the chart once they do. */}
              {byType && <BarCard title="By dataset type" rows={typeRows} />}
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
                {r.count.toLocaleString("en-IN")}
                <span className="sr-only"> {r.count === 1 ? "dataset" : "datasets"}</span>
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
