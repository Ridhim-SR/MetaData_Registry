import type { AccessLevel } from "../../api/registry";

export type ExtendedAccessLevel = AccessLevel | "confidential";

const labels: Record<ExtendedAccessLevel, string> = {
  public: "Public",
  department: "Department-only",
  restricted: "Restricted",
  confidential: "Confidential",
};

const badgeClass: Record<ExtendedAccessLevel, string> = {
  public: "badge badge-public",
  department: "badge badge-department",
  restricted: "badge badge-restricted",
  confidential: "badge badge-confidential",
};

/** Small inline SVG icons so the badge never relies on color alone. */
function BadgeIcon({ level }: { level: ExtendedAccessLevel }) {
  const common = {
    width: 12,
    height: 12,
    viewBox: "0 0 16 16",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round",
    strokeLinejoin: "round",
    "aria-hidden": true,
  } as const;
  if (level === "public")
    return (
      <svg {...common}>
        <circle cx="8" cy="8" r="6" />
        <path d="M2 8h12M8 2c2.5 2 2.5 10 0 12M8 2c-2.5 2-2.5 10 0 12" />
      </svg>
    );
  if (level === "department")
    return (
      <svg {...common}>
        <rect x="2.5" y="3" width="11" height="10" rx="1" />
        <path d="M6 6h1.5M8.5 6H10M6 8.5h1.5M8.5 8.5H10M6 11h4" />
      </svg>
    );
  if (level === "confidential")
    return (
      <svg {...common}>
        <rect x="3" y="7" width="10" height="6" rx="1" />
        <path d="M5.5 7V5.5a2.5 2.5 0 0 1 5 0V7" />
        <circle cx="8" cy="10" r="1" fill="currentColor" stroke="none" />
      </svg>
    );
  return (
    <svg {...common}>
      <rect x="3" y="7" width="10" height="6" rx="1" />
      <path d="M5.5 7V5.5a2.5 2.5 0 0 1 5 0V7" />
    </svg>
  );
}

export function AccessBadge({ level }: { level: AccessLevel | string | undefined }) {
  const normalized: ExtendedAccessLevel =
    level === "public" || level === "restricted" || level === "confidential"
      ? level
      : "department";
  return (
    <span className={badgeClass[normalized]}>
      <BadgeIcon level={normalized} />
      {labels[normalized]}
    </span>
  );
}
