import { useState } from "react";
import { Link } from "react-router-dom";
import type { DatasetCard as Card, RegistryTable } from "../../api/registry";
import { requestAccess } from "../../api/registry";
import { completenessPct, humanizeRaw, orNotProvided } from "../../utils/format";
import { useAuth } from "../../contexts/AuthContext";
import { AccessBadge } from "./AccessBadge";

export function DatasetCard({ card }: { card: Card }) {
  const dept = card.department_display ?? card.department ?? "Not provided";
  const description = (card.tables ?? []).map((t) => t.description?.trim()).find(Boolean)
    ?? card.description?.trim()
    ?? "";
  const completeness = completenessPct(card.tables ?? []);

  return (
    <article
      className="flex flex-col p-5"
      style={{ border: "1px solid var(--border)", borderRadius: 6, background: "var(--bg)" }}
    >
      <div className="flex items-start justify-between gap-2">
        <h3
          className="min-w-0 flex-1 text-base font-semibold"
          style={{ fontSize: "1rem", overflowWrap: "anywhere" }}
        >
          <Link
            to={`/datasets/${encodeURIComponent(card.dataset)}`}
            style={{ color: "var(--blue-700)" }}
          >
            {humanizeRaw(card.name)}
          </Link>
        </h3>
        <span style={{ flexShrink: 0 }}>
          <AccessBadge level={card.access_level} />
        </span>
      </div>
      <p className="mt-1 text-sm" style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
        {humanizeRaw(dept === "Not provided" ? null : dept)}
      </p>
      {description ? (
        <p className="clamp-2 mt-2 text-sm" style={{ color: "var(--text)", fontSize: "0.9375rem" }}>
          {description}
        </p>
      ) : (
        <p className="not-provided mt-2 text-sm" style={{ fontSize: "0.9375rem" }}>
          Not provided
        </p>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <span className="badge badge-neutral">Metadata {completeness}%</span>
        <span className="text-sm" style={{ color: "var(--text-muted)", fontSize: "0.8125rem" }}>
          {card.table_count} {card.table_count === 1 ? "table" : "tables"}
        </span>
      </div>
      <div className="mt-2 flex-1" />
      <p className="mt-2 text-sm" style={{ color: "var(--text-muted)", fontSize: "0.8125rem" }}>
        Last updated:{" "}
        <span className="not-provided">{orNotProvided(undefined)}</span>
      </p>
      <Link
        to={`/datasets/${encodeURIComponent(card.dataset)}`}
        className="btn-secondary mt-3 w-fit"
        style={{ padding: "0.4rem 1rem", fontSize: "0.875rem" }}
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

  const dept = table.department_display ?? table.department ?? "Not provided";

  return (
    <article
      className="flex flex-col p-5"
      style={{ border: "1px solid var(--border)", borderRadius: 6, background: "var(--bg)" }}
    >
      <div className="flex items-start justify-between gap-2">
        <h3 className="text-base font-semibold" style={{ fontSize: "1rem", color: "var(--navy-900)" }}>
          {table.name || "Not provided"}
        </h3>
        <AccessBadge level="restricted" />
      </div>
      <p className="mt-1 text-sm" style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
        {dept}
      </p>
      <p className="mt-2 text-sm" style={{ color: "var(--text)", fontSize: "0.9375rem" }}>
        Access requires authorization.
      </p>
      <div className="mt-4 flex-1" />
      {state === "sent" ? (
        <p className="text-sm font-medium" role="status" style={{ color: "var(--public-fg)" }}>
          Access requested. The owning department will review your request.
        </p>
      ) : isAuthenticated ? (
        <button
          onClick={onRequest}
          disabled={state === "sending"}
          className="btn-primary w-fit"
          style={{ padding: "0.4rem 1rem", fontSize: "0.875rem" }}
        >
          {state === "sending" ? "Requesting…" : "Request Access"}
        </button>
      ) : (
        <Link
          to="/login"
          className="btn-primary w-fit"
          style={{ padding: "0.4rem 1rem", fontSize: "0.875rem" }}
        >
          Sign in to request access
        </Link>
      )}
      {state === "error" && (
        <p className="mt-2 text-sm" role="alert" style={{ color: "var(--confid-fg)" }}>
          Could not send the request. Please try again.
        </p>
      )}
    </article>
  );
}
