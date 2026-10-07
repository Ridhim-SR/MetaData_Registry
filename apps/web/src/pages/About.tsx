import { Link } from "react-router-dom";

export function AboutPage() {
  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-10 sm:px-6">
      <Link to="/" className="mb-4 inline-block text-sm font-medium underline" style={{ color: "var(--blue-700)" }}>
        ← Back to home
      </Link>
      <h1 className="font-bold" style={{ color: "var(--navy-900)", fontSize: "1.75rem" }}>About</h1>
      <div className="mt-4 space-y-4 text-sm leading-relaxed" style={{ color: "var(--text)", fontSize: "0.9375rem" }}>
        <p>
          The SDA Metadata Registry is the official metadata catalogue of the
          Government of Uttar Pradesh. It describes datasets held by state
          departments — what each dataset contains, which department owns it,
          and who is allowed to access it.
        </p>
        <p>
          The registry publishes metadata (titles, structure, ownership and
          access levels), not raw data records. Datasets marked Public can be
          explored by anyone. Department-only and Restricted datasets show a
          summary; full details require signing in with a department account
          or requesting access from the owning department.
        </p>
        <p>
          Departments are listed in the{" "}
          <Link to="/departments" className="underline" style={{ color: "var(--blue-700)" }}>
            Department Directory
          </Link>
          , and every dataset can be found through the{" "}
          <Link to="/explore" className="underline" style={{ color: "var(--blue-700)" }}>
            Catalog
          </Link>
          .
        </p>
      </div>
    </div>
  );
}
