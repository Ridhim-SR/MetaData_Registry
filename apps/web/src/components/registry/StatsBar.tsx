import { useQuery } from "@tanstack/react-query";
import { getRegistryStats } from "../../api/registry";
import { ErrorBlock, Skeleton } from "./StateBlocks";

export function StatsBar() {
  const query = useQuery({ queryKey: ["registry-stats"], queryFn: getRegistryStats });
  // Show the loader on every fetch so stale counts never flash as current.
  const loading = query.isPending || query.isFetching;

  return (
    <section
      aria-label="Catalog statistics"
      style={{ background: "var(--bg-alt)", borderTop: "1px solid var(--border)", borderBottom: "1px solid var(--border)" }}
    >
      <div className="mx-auto w-full max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        {loading && (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3" role="status" aria-label="Loading statistics">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-20" />
            ))}
          </div>
        )}
        {!loading && query.error && (
          <ErrorBlock
            message="Unable to load catalog information. Please try again."
            onRetry={() => query.refetch()}
          />
        )}
        {!loading && query.data && (
          <dl className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            {[
              { label: "Departments", value: query.data.departments },
              { label: "Datasets", value: query.data.datasets },
              { label: "Tables", value: query.data.tables },
            ].map((s) => (
              <div
                key={s.label}
                className="px-5 py-4 text-center"
                style={{ border: "1px solid var(--border)", borderRadius: 6, background: "var(--bg)" }}
              >
                <dt style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>{s.label}</dt>
                <dd
                  className="mt-1 font-bold"
                  style={{ color: "var(--navy-900)", fontSize: "2rem", lineHeight: 1.2 }}
                >
                  {s.value.toLocaleString("en-IN")}
                </dd>
              </div>
            ))}
          </dl>
        )}
      </div>
    </section>
  );
}
