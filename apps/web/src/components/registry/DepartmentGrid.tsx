import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { listDepartments } from "../../api/registry";
import { EmptyBlock, ErrorBlock, Skeleton } from "./StateBlocks";

const icons = ["🌾", "🏥", "🏗", "💧", "🏭", "📚", "🏘", "🗺", "🤝", "📊", "💻"];
function iconFor(name: string, index: number) {
  void name;
  return icons[index % icons.length];
}

export function DepartmentGrid({ compact = false }: { compact?: boolean }) {
  const query = useQuery({ queryKey: ["registry-departments"], queryFn: listDepartments });

  return (
    <section aria-label="Browse by department" className="mx-auto w-full max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
      <h2 className="text-xl font-semibold text-slate-900">Browse by Department</h2>
      {query.isPending && (
        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4" role="status" aria-label="Loading departments">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
      )}
      {query.error && (
        <div className="mt-4">
          <ErrorBlock message="Unable to load departments. Please try again." onRetry={() => query.refetch()} />
        </div>
      )}
      {query.data && query.data.items.length === 0 && (
        <div className="mt-4">
          <EmptyBlock title="No departments yet" body="Departments will appear here once metadata is published to the registry." />
        </div>
      )}
      {query.data && query.data.items.length > 0 && (
        <ul className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {(compact ? query.data.items.slice(0, 8) : query.data.items).map((d, i) => (
            <li key={d.name}>
              <Link
                to={`/explore?department=${encodeURIComponent(d.name)}`}
                className="block rounded-lg border border-slate-200 bg-white p-4 transition-shadow hover:shadow-md focus:ring-2 focus:ring-slate-900 focus:outline-none"
              >
                <div className="text-2xl" aria-hidden>
                  {iconFor(d.name, i)}
                </div>
                <div className="mt-2 text-sm font-semibold text-slate-900">{d.name}</div>
                <div className="mt-1 text-xs text-slate-500">
                  {d.dataset_count} datasets · {d.table_count} tables
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
