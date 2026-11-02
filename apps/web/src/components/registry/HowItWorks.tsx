import { t, useLanguage } from "../../i18n";
import type { I18nKey } from "../../i18n";

const steps: Array<{ icon: string; title: I18nKey; body: I18nKey }> = [
  {
    icon: "🧭",
    title: "howDiscover",
    body: "howDiscoverBody",
  },
  {
    icon: "🔍",
    title: "howSearch",
    body: "howSearchBody",
  },
  {
    icon: "📖",
    title: "howUnderstand",
    body: "howUnderstandBody",
  },
  {
    icon: "🔑",
    title: "howAccess",
    body: "howAccessBody",
  },
];

export function HowItWorks() {
  useLanguage();
  return (
    <section
      aria-label={t("howTitle")}
      style={{ background: "var(--bg-alt)", borderTop: "1px solid var(--border)" }}
    >
      <div className="page-container mx-auto w-full max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
        <h2 className="font-semibold" style={{ color: "var(--navy-900)", fontSize: "1.375rem" }}>
          {t("howTitle")}
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
                  {t("howStep", { n: i + 1 })}
                </span>
              </div>
              <h3 className="mt-2 font-semibold" style={{ fontSize: "1rem" }}>
                {t(s.title)}
              </h3>
              <p className="mt-1 text-sm" style={{ color: "var(--text-muted)", fontSize: "0.9375rem" }}>
                {t(s.body)}
              </p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
