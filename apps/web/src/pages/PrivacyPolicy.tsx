import { Link } from "react-router-dom";

export function PrivacyPolicyPage() {
  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-10 sm:px-6">
      <Link to="/" className="mb-4 inline-block text-sm font-medium underline" style={{ color: "var(--blue-700)" }}>
        ← Back to home
      </Link>
      <h1 className="text-2xl font-bold" style={{ color: "var(--navy-900)" }}>Data Privacy Policy</h1>
      <p className="mt-4 text-sm leading-relaxed" style={{ color: "var(--text)" }}>
        The SDA Metadata Registry is a metadata catalogue: it describes datasets (titles,
        tables, columns, ownership and access levels) and does not publish raw data records.
        The formal data privacy policy for this portal will be published here.
      </p>
    </div>
  );
}
