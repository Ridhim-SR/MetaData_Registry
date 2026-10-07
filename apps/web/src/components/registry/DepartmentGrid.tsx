import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { listDepartments } from "../../api/registry";
import { humanizeRaw } from "../../utils/format";
import { EmptyBlock, ErrorBlock, Skeleton } from "./StateBlocks";

const icons = ["🌾", "🏥", "🏗", "💧", "🏭", "📚", "🏘", "🗺"];
function iconFor(index: number) {
  return icons[index % icons.length];
}

export function DepartmentGrid({ compact = false }: { compact?: boolean }) {
  const query = useQuery({ queryKey: ["registry-departments"], queryFn: listDepartments });

  const sortedTop = query.data
    ? [...query.data.items].sort((a, b) => b.dataset_count - a.dataset_count)
    : [];
  // Show the loader on every fetch so stale tiles never flash as current.
  const loading = query.isPending || query.isFetching;
  const total = query.data?.total ?? 0;
  const shown = compact ? sortedTop.slice(0, 8) : sortedTop;

  return (
    <section
      aria-label="Top departments"
      className="mx-auto w-full max-w-7xl px-4 py-10 sm:px-6 lg:px-8"
    >
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="font-semibold" style={{ color: "var(--navy-900)", fontSize: "1.375rem" }}>
            Top Departments
          </h2>
          <p className="mt-1 text-sm" style={{ color: "var(--text-muted)", fontSize: "0.9375rem" }}>
            Departments with the most published datasets.
          </p>
        </div>
        {compact && total > 0 && (
          <Link
            to="/departments"
            className="font-semibold"
            style={{ color: "var(--blue-700)", fontSize: "1rem" }}
          >
            View all {total} departments →
          </Link>
        )}
      </div>

      {loading && (
        <div
          className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4"
          role="status"
          aria-label="Loading departments"
        >
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
      )}
      {!loading && query.error && (
        <div className="mt-4">
          <ErrorBlock message="Unable to load departments. Please try again." onRetry={() => query.refetch()} />
        </div>
      )}
      {!loading && query.data && query.data.items.length === 0 && (
        <div className="mt-4">
          <EmptyBlock
            title="No departments published yet."
            body="Departments will appear here once metadata is published."
          />
        </div>
      )}
      {!loading && query.data && shown.length > 0 && (
        <ul className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {shown.map((d, i) => (
            <li key={d.slug}>
              <Link
                to={`/departments/${encodeURIComponent(d.slug)}`}
                className="block p-4"
                style={{
                  border: "1px solid var(--border)",
                  borderRadius: 6,
                  background: "var(--bg)",
                  textDecoration: "none",
                }}
              >
                <div className="text-2xl" aria-hidden style={{ color: "var(--saffron-text)" }}>
                  {iconFor(i)}
                </div>
                <div className="mt-2 font-semibold" style={{ color: "var(--navy-900)", fontSize: "1rem" }}>
                  {humanizeRaw(d.display_name)}
                </div>
                <div className="mt-1 text-sm" style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
                  {d.dataset_count} {d.dataset_count === 1 ? "dataset" : "datasets"}
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
      {compact && total > 8 && (
        <p className="mt-4 text-center">
          <Link to="/departments" className="btn-secondary" style={{ fontSize: "0.9375rem" }}>
            View all {total} departments →
          </Link>
        </p>
      )}
    </section>
  );
}
