import { Link } from "react-router-dom";

export function ContactPage() {
  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-10 sm:px-6">
      <Link to="/" className="mb-4 inline-block text-sm font-medium underline" style={{ color: "var(--blue-700)" }}>
        ← Back to home
      </Link>
      <h1 className="font-bold" style={{ color: "var(--navy-900)", fontSize: "1.75rem" }}>Contact</h1>
      <div className="mt-4 space-y-4 text-sm leading-relaxed" style={{ color: "var(--text)", fontSize: "0.9375rem" }}>
        <p>
          For questions about a specific dataset, open its page in the{" "}
          <Link to="/explore" className="underline" style={{ color: "var(--blue-700)" }}>
            Catalog
          </Link>{" "}
          and use the Request Access button — the owning department reviews
          each request.
        </p>
        <p>
          Each department&apos;s page in the{" "}
          <Link to="/departments" className="underline" style={{ color: "var(--blue-700)" }}>
            Department Directory
          </Link>{" "}
          lists its published contact details where the department has
          provided them.
        </p>
        <p>
          For account issues such as sign-in problems or a missing department
          on your account, contact your department&apos;s nodal officer or the
          registry administrator.
        </p>
      </div>
    </div>
  );
}
