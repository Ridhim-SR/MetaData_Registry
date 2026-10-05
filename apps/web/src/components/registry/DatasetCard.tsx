import { useState } from "react";
import { Link } from "react-router-dom";
import type { DatasetCard as Card, RegistryTable } from "../../api/registry";
import { requestAccess } from "../../api/registry";
import { capitalizeFirst } from "../../utils/format";
import { useAuth } from "../../contexts/AuthContext";
import { AccessBadge } from "./AccessBadge";

function tableWord(n: number) {
  return `${n} ${n === 1 ? "Table" : "Tables"}`;
}

export function DatasetCard({ card }: { card: Card }) {
  return (
    <article className="flex flex-col rounded-lg border border-slate-200 bg-white p-5">
      <div className="flex items-start justify-between gap-2">
        <h3 className="text-base font-semibold text-slate-900">{capitalizeFirst(card.name)}</h3>
        <AccessBadge level={card.access_level} />
      </div>
      <p className="mt-1 text-sm text-slate-500">
        {[card.department ?? card.service, card.database]
          .map((part) => capitalizeFirst(part))
          .filter(Boolean)
          .join(" · ")}
      </p>
      <p className="mt-2 text-sm text-slate-600">{tableWord(card.table_count)}</p>
      <div className="mt-4 flex-1" />
      <Link
        to={`/datasets/${encodeURIComponent(card.dataset)}`}
        className="inline-flex w-fit rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 focus:ring-2 focus:ring-slate-900 focus:ring-offset-2 focus:outline-none"
      >
        View Dataset
      </Link>
    </article>
  );
}

export function RestrictedTeaser({ table }: { table: RegistryTable }) {
  const { isAuthenticated } = useAuth();
  const [state, setState] = useState<"idle" | "sending" | "sent" | "error">("idle");

  const onRequest = async () => {
    setState("sending");
    try {
      await requestAccess(table.fullyQualifiedName);
      setState("sent");
    } catch {
      setState("error");
    }
  };

  return (
    <article className="flex flex-col rounded-lg border border-amber-200 bg-amber-50 p-5">
      <div className="flex items-start justify-between gap-2">
        <h3 className="text-base font-semibold text-slate-900">{capitalizeFirst(table.name)}</h3>
        <AccessBadge level="restricted" />
      </div>
      <p className="mt-1 text-sm text-slate-500">{capitalizeFirst(table.department)}</p>
      <p className="mt-2 text-sm text-slate-600">Access requires authorization.</p>
      <div className="mt-4 flex-1" />
      {state === "sent" ? (
        <p className="text-sm font-medium text-green-700" role="status">
          Access requested. The owning department will review your request.
        </p>
      ) : isAuthenticated ? (
        <button
          onClick={onRequest}
          disabled={state === "sending"}
          className="inline-flex w-fit rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-60"
        >
          {state === "sending" ? "Requesting…" : "Request Access"}
        </button>
      ) : (
        <Link
          to="/login"
          className="inline-flex w-fit rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700"
        >
          Sign in to request access
        </Link>
      )}
      {state === "error" && (
        <p className="mt-2 text-sm text-red-700" role="alert">
          Could not send the request. Please try again.
        </p>
      )}
    </article>
  );
}
