import { DepartmentGrid } from "../components/registry/DepartmentGrid";

export function DepartmentsPage() {
  return (
    <div style={{ background: "var(--bg)" }}>
      <div className="mx-auto w-full max-w-7xl px-4 pt-8 sm:px-6 lg:px-8">
        <h1 className="font-bold" style={{ color: "var(--navy-900)", fontSize: "1.75rem" }}>
          Department Directory
        </h1>
        <p className="mt-1 text-sm" style={{ color: "var(--text-muted)", fontSize: "0.9375rem" }}>
          Browse metadata by department. Select a department to see its datasets.
        </p>
      </div>
      <DepartmentGrid />
    </div>
  );
}
