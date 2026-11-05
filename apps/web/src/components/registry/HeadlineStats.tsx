import { Link } from "react-router-dom";
import type { RegistryStats } from "../../api/registry";
import { formatNumber, t } from "../../i18n";
import { IconTile } from "./Icons";
import type { IconName } from "./Icons";

type Stat = { key: string; icon: IconName; label: string; value: number; to: string };

/** The three headline registry counts, shown at the top of "Datasets at a glance". */
export function HeadlineStats({ stats: s }: { stats: RegistryStats }) {
  const stats: Stat[] = [
    { key: "departments", icon: "landmark", label: t("tabDepartments"), value: s.departments, to: "/departments" },
    { key: "datasets", icon: "database", label: t("tabDatasets"), value: s.datasets, to: "/explore?scope=datasets" },
    { key: "tables", icon: "table", label: t("tabTables"), value: s.tables, to: "/explore?scope=tables" },
  ];

  return (
    <dl
      aria-label={t("statsAria")}
      className="grid grid-cols-1 gap-y-5 px-2 py-5 sm:grid-cols-3"
      style={{ border: "1px solid var(--border)", borderRadius: 6, background: "var(--bg)" }}
    >
      {stats.map((x, i) => (
        <div
          key={x.key}
          className={`flex items-center gap-4 px-3 sm:px-5 ${i > 0 ? "sm:border-l" : ""}`}
          style={{ borderColor: "var(--border)" }}
        >
          <IconTile name={x.icon} />
          <div className="flex min-w-0 flex-col-reverse">
            <dt style={{ fontSize: "0.875rem" }}>
              <Link to={x.to} className="stat-link" style={{ color: "var(--text-muted)" }}>
                {x.label}
              </Link>
            </dt>
            <dd className="font-bold" style={{ color: "var(--navy-900)", fontSize: "1.75rem", lineHeight: 1.1 }}>
              {formatNumber(x.value)}
            </dd>
          </div>
        </div>
      ))}
    </dl>
  );
}
