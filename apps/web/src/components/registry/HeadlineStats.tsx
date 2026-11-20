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
    <dl aria-label={t("statsAria")} className="grid grid-cols-1 gap-4 sm:grid-cols-3">
      {stats.map((x) => (
        <div
          key={x.key}
          className="flex items-center justify-center gap-4 px-5 py-5"
          style={{ border: "1px solid var(--border)", borderRadius: 6, background: "var(--bg-alt)" }}
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
