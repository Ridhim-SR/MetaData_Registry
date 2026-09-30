import { useQuery } from "@tanstack/react-query";
import { getRegistryStats } from "../../api/registry";
import { ErrorBlock, Skeleton } from "./StateBlocks";

export function StatsBar() {
  const query = useQuery({ queryKey: ["registry-stats"], queryFn: getRegistryStats });

  return (
    <section aria-label="Catalog statistics" className="border-b border-slate-200 bg-slate-50">
      {/* Shared page container: 1280px cap, centered, responsive gutters */}
      <div className="mx-auto w-full max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        <h2 className="text-sm font-semibold tracking-wider text-slate-500 uppercase">Explore the catalog</h2>
        {query.isPending && (
          <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-3" role="status" aria-label="Loading statistics">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-20" />
            ))}
          </div>
        )}
        {query.error && (
          <div className="mt-4">
            <ErrorBlock
              message="Unable to load catalog information. Please try again."
              onRetry={() => query.refetch()}
            />
          </div>
        )}
        {query.data && (
          <dl className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-3">
            {[
              { label: "Departments", value: query.data.departments },
              { label: "Datasets", value: query.data.datasets },
              { label: "Tables", value: query.data.tables },
            ].map((s) => (
              <div key={s.label} className="rounded-lg border border-slate-200 bg-white px-5 py-4">
                <dt className="text-sm text-slate-500">{s.label}</dt>
                <dd className="mt-1 text-3xl font-bold text-slate-900">{s.value.toLocaleString()}</dd>
              </div>
            ))}
          </dl>
        )}
      </div>
    </section>
  );
}
