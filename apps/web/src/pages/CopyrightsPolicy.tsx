import { Link } from "react-router-dom";

export function CopyrightsPolicyPage() {
  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-10 sm:px-6">
      <Link to="/" className="mb-4 inline-block text-sm font-medium text-slate-900 underline">
        ← Back to home
      </Link>
      <h1 className="text-2xl font-bold text-slate-900">Copyrights Policy</h1>
      <p className="mt-4 text-sm leading-relaxed text-slate-600">
        Metadata published on the SDA Metadata Registry remains the property of the owning
        department. The formal copyrights policy for this portal will be published here.
      </p>
    </div>
  );
}
