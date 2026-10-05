import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { listPublicDatasets } from "../../api/registry";
import { DatasetCard } from "./DatasetCard";
import { EmptyBlock, ErrorBlock, Skeleton } from "./StateBlocks";

export function PublicDataSection() {
  const query = useQuery({ queryKey: ["registry-public"], queryFn: listPublicDatasets });

  return (
    <section aria-label="Public data" className="border-y border-slate-200 bg-slate-50">
      <div className="mx-auto w-full max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
        <h2 className="text-xl font-semibold text-slate-900">Public Data</h2>
        <p className="mt-1 text-sm text-slate-600">Explore datasets available without signing in.</p>

        {query.isPending && (
          <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3" role="status" aria-label="Loading public datasets">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-44" />
            ))}
          </div>
        )}

        {query.error && (
          <div className="mt-4">
            <ErrorBlock
              message="Public dataset information is temporarily unavailable."
              onRetry={() => query.refetch()}
            />
          </div>
        )}

        {query.data && query.data.items.length === 0 && (
          <div className="mt-4">
            <EmptyBlock
              title="No public datasets are currently available."
              body="The registry contains metadata from participating departments. Public datasets will appear here as they are published."
              action={
                <Link
                  to="/explore"
                  className="inline-flex rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700"
                >
                  Explore Full Catalog
                </Link>
              }
            />
          </div>
        )}

        {query.data && query.data.items.length > 0 && (
          <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {query.data.items.map((card) => (
              <DatasetCard key={card.dataset} card={card} />
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
