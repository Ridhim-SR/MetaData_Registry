const steps = [
  {
    icon: "🧭",
    title: "Discover",
    body: "Browse departments and the full catalog.",
  },
  {
    icon: "🔍",
    title: "Search",
    body: "Find datasets, tables or columns by keyword.",
  },
  {
    icon: "📖",
    title: "Understand",
    body: "Check structure, ownership and access level.",
  },
  {
    icon: "🔑",
    title: "Access",
    body: "View public data or request department access.",
  },
];

export function HowItWorks() {
  return (
    <section
      aria-label="How it works"
      style={{ background: "var(--bg-alt)", borderTop: "1px solid var(--border)" }}
    >
      <div className="mx-auto w-full max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
        <h2 className="font-semibold" style={{ color: "var(--navy-900)", fontSize: "1.375rem" }}>
          How It Works
        </h2>
        <ol className="mt-4 grid list-none grid-cols-1 gap-4 p-0 sm:grid-cols-2 lg:grid-cols-4">
          {steps.map((s, i) => (
            <li
              key={s.title}
              className="p-5"
              style={{ border: "1px solid var(--border)", borderRadius: 6, background: "var(--bg)" }}
            >
              <div className="flex items-center gap-2">
                <span aria-hidden style={{ fontSize: "1.5rem", color: "var(--saffron-text)" }}>
                  {s.icon}
                </span>
                <span style={{ color: "var(--text-muted)", fontSize: "0.8125rem", fontWeight: 600 }}>
                  Step {i + 1}
                </span>
              </div>
              <h3 className="mt-2 font-semibold" style={{ fontSize: "1rem" }}>
                {s.title}
              </h3>
              <p className="mt-1 text-sm" style={{ color: "var(--text-muted)", fontSize: "0.9375rem" }}>
                {s.body}
              </p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
