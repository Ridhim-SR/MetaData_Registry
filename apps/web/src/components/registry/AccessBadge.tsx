import type { AccessLevel } from "../../api/registry";

const styles: Record<AccessLevel, string> = {
  public: "bg-green-100 text-green-800 border-green-200",
  department: "bg-blue-100 text-blue-800 border-blue-200",
  restricted: "bg-amber-100 text-amber-900 border-amber-200",
};

const labels: Record<AccessLevel, string> = {
  public: "Public",
  department: "Department",
  restricted: "Restricted",
};

const icons: Record<AccessLevel, string> = {
  public: "🌐",
  department: "🏢",
  restricted: "🔒",
};

export function AccessBadge({ level }: { level: AccessLevel | undefined }) {
  const normalized: AccessLevel = level === "public" || level === "restricted" ? level : "department";
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium ${styles[normalized]}`}
    >
      <span aria-hidden>{icons[normalized]}</span>
      {labels[normalized]}
    </span>
  );
}
