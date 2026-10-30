import { useId, type ReactNode } from "react";
import { t } from "../../i18n";
import { completenessSummary, type CompletenessItem } from "../../utils/format";

const scoreColor = (pct: number) =>
  pct < 40 ? "var(--confid-fg)" : pct < 80 ? "var(--restricted-fg)" : "var(--public-fg)";

/**
 * Compact completeness meter for pages whose facts are already listed on
 * screen: just the percentage and a bar. Hover or focus reveals the item
 * breakdown behind the percentage, so the page does not repeat "Not provided".
 */
export function CompletenessMeter({
  label,
  items,
  note,
}: {
  label: string;
  items: CompletenessItem[];
  note?: ReactNode;
}) {
  const { done, pct } = completenessSummary(items);
  const color = scoreColor(pct);
  const tipId = useId();

  return (
    <div className="completeness-meter" tabIndex={0} aria-describedby={tipId}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: "0.75rem" }}>
        <span style={{ color: "var(--text-muted)", fontSize: "0.8125rem", fontWeight: 600 }}>{label}</span>
        <span style={{ color, fontSize: "1.125rem", fontWeight: 700, lineHeight: 1 }}>{pct}%</span>
      </div>
      <div
        role="progressbar"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={label}
        style={{ marginTop: "6px", height: "6px", borderRadius: 999, background: "var(--bg-alt)" }}
      >
        <div style={{ width: `${pct}%`, height: "100%", borderRadius: 999, background: color }} />
      </div>
      <div id={tipId} role="tooltip" className="completeness-meter-pop">
        <p style={{ fontWeight: 600 }}>
          {t("documentedCount", { done: String(done), total: String(items.length) })}
        </p>
        <ul style={{ marginTop: "4px" }}>
          {items.map((i) => {
            const isDone = i.score >= 1;
            return (
              <li key={i.key} className="completeness-meter-row" style={{ opacity: isDone ? 1 : 0.8 }}>
                {isDone ? (
                  <span aria-hidden className="completeness-meter-check">
                    ✓
                  </span>
                ) : (
                  <span aria-hidden className="completeness-meter-todo" />
                )}
                <span style={{ flex: 1 }}>{i.label}</span>
                {i.count !== null && <span style={{ opacity: 0.75, whiteSpace: "nowrap" }}>{i.count}</span>}
              </li>
            );
          })}
        </ul>
        {note && <p className="completeness-meter-note">{note}</p>}
      </div>
    </div>
  );
}

/**
 * Metadata-completeness card shared by the dataset and table pages. Each page
 * passes only the items that belong to its own entity; `footer` carries any
 * extra context (e.g. a roll-up) that is shown but not scored.
 */
export function CompletenessCard({
  title,
  tooltip,
  items,
  footer,
}: {
  title: string;
  tooltip: string;
  items: CompletenessItem[];
  footer?: ReactNode;
}) {
  const { done, pct } = completenessSummary(items);
  const color = scoreColor(pct);

  return (
    <div style={{ border: "0.5px solid var(--border)", borderRadius: 12, background: "var(--bg)", padding: "12px 16px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.5rem" }}>
        <h2
          className="font-semibold"
          style={{ display: "flex", alignItems: "center", gap: "0.35rem", color: "var(--navy-900)", fontSize: "1rem" }}
        >
          {title}
          <span
            tabIndex={0}
            aria-label={tooltip}
            className="completeness-info"
            style={{
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              width: "16px",
              height: "16px",
              borderRadius: "50%",
              border: "1px solid var(--text-muted)",
              color: "var(--text-muted)",
              fontSize: "11px",
              fontWeight: 700,
            }}
          >
            <span aria-hidden="true">i</span>
            <span role="tooltip" className="completeness-info-tip">
              {tooltip}
            </span>
          </span>
        </h2>
        <span style={{ color, fontSize: "1rem", fontWeight: 700 }}>{pct}%</span>
      </div>
      <div
        role="progressbar"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={title}
        className="mt-2"
        style={{ height: "6px", borderRadius: 999, background: "var(--bg-alt)" }}
      >
        <div style={{ width: `${pct}%`, height: "100%", borderRadius: 999, background: color }} />
      </div>
      <p className="mt-1" style={{ color: "var(--text-muted)", fontSize: "0.8125rem" }}>
        {t("documentedCount", { done: String(done), total: String(items.length) })}
      </p>
      <ul className="mt-1" style={{ fontSize: "0.875rem" }}>
        {items.map((item) => {
          const isDone = item.score >= 1;
          return (
            <li
              key={item.key}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0.5rem",
                borderTop: "1px solid var(--border)",
                paddingTop: "7px",
                paddingBottom: "7px",
                color: isDone ? "var(--text)" : "var(--text-muted)",
              }}
            >
              {isDone ? (
                <span aria-hidden style={{ color: "var(--public-fg)", fontWeight: 700 }}>
                  ✓
                </span>
              ) : (
                <span
                  aria-hidden
                  style={{
                    width: "14px",
                    height: "14px",
                    flexShrink: 0,
                    borderRadius: "50%",
                    border: "1.5px dashed var(--text-muted)",
                  }}
                />
              )}
              <span className="min-w-0 flex-1">{item.label}</span>
              {item.count !== null && (
                <span style={{ color: "var(--text-muted)", fontSize: "0.8125rem", whiteSpace: "nowrap" }}>
                  {item.count}
                </span>
              )}
            </li>
          );
        })}
      </ul>
      {footer && (
        <div
          style={{
            borderTop: "1px solid var(--border)",
            paddingTop: "7px",
            color: "var(--text-muted)",
            fontSize: "0.8125rem",
          }}
        >
          {footer}
        </div>
      )}
    </div>
  );
}
