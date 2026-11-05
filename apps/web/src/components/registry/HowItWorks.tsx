import { t, useLanguage } from "../../i18n";
import type { I18nKey } from "../../i18n";
import { Icon } from "./Icons";
import type { IconName } from "./Icons";

const steps: Array<{ icon: IconName; title: I18nKey; body: I18nKey }> = [
  { icon: "landmark", title: "howS1Title", body: "howS1Body" },
  { icon: "fileUp", title: "howS2Title", body: "howS2Body" },
  { icon: "database", title: "howS3Title", body: "howS3Body" },
  { icon: "laptopSearch", title: "howS4Title", body: "howS4Body" },
  { icon: "users", title: "howS5Title", body: "howS5Body" },
  { icon: "refresh", title: "howS6Title", body: "howS6Body" },
];

const benefits: Array<{ icon: IconName; label: I18nKey }> = [
  { icon: "search", label: "howBenefitAccess" },
  { icon: "handshake", label: "howBenefitInterop" },
  { icon: "shieldCheck", label: "howBenefitGovernance" },
  { icon: "trendingUp", label: "howBenefitDecisions" },
];

const panel: React.CSSProperties = {
  border: "1px solid color-mix(in srgb, var(--blue-700) 22%, transparent)",
  borderRadius: 14,
  background: "var(--bg)",
};

/** The registry process in six steps, the SDA's role, and the benefits. */
export function HowItWorks() {
  useLanguage();
  return (
    <section
      id="how-it-works"
      aria-labelledby="how-it-works-title"
      style={{ background: "color-mix(in srgb, var(--blue-50) 70%, var(--bg))", borderTop: "1px solid var(--border)" }}
    >
      <div className="page-container mx-auto w-full max-w-7xl px-4 py-14 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-4xl text-center">
          <h2
            id="how-it-works-title"
            className="font-bold"
            style={{ color: "var(--navy-900)", fontSize: "clamp(1.5rem, 3vw, 2.125rem)", lineHeight: 1.2 }}
          >
            {t("howHeading")}
          </h2>
          <div
            aria-hidden="true"
            className="mx-auto mt-3"
            style={{ width: 96, height: 3, borderRadius: 2, background: "var(--saffron)" }}
          />
          <p className="mt-4" style={{ color: "var(--text)", fontSize: "1.0625rem" }}>
            {t("howIntro")}
          </p>
        </div>

        <ol className="mt-12 grid list-none grid-cols-1 gap-x-10 gap-y-10 p-0 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 xl:gap-x-8">
          {steps.map((s, i) => (
            <li key={s.title} className="relative">
              <div className="flex h-full flex-col text-center" style={{ ...panel, paddingTop: 28 }}>
                <span
                  className="absolute left-1/2 flex -translate-x-1/2 items-center justify-center font-bold"
                  style={{
                    top: -18,
                    width: 36,
                    height: 36,
                    borderRadius: 999,
                    background: "var(--navy-900)",
                    color: "#fff",
                    fontSize: "1rem",
                    boxShadow: "0 0 0 4px color-mix(in srgb, var(--blue-50) 70%, var(--bg))",
                  }}
                >
                  <span className="sr-only">{t("howStepLabel", { n: i + 1 })}: </span>
                  {i + 1}
                </span>
                <h3 className="px-4 font-bold" style={{ color: "var(--navy-900)", fontSize: "1.0625rem", lineHeight: 1.3 }}>
                  {t(s.title)}
                </h3>
                <span className="mx-auto mt-4" style={{ color: "var(--blue-700)" }}>
                  <Icon name={s.icon} size={52} />
                </span>
                <p className="mt-4 flex-1 px-4 pb-6" style={{ color: "var(--text-muted)", fontSize: "0.9375rem" }}>
                  {t(s.body)}
                </p>
              </div>
              {i < steps.length - 1 && (
                <span
                  aria-hidden="true"
                  className="absolute hidden xl:flex"
                  style={{ top: "45%", right: -28, color: "var(--navy-900)" }}
                >
                  <Icon name="arrowRight" size={22} />
                </span>
              )}
            </li>
          ))}
        </ol>

        <div className="mt-10 flex flex-col gap-4 p-6 sm:flex-row sm:items-center sm:gap-6" style={panel}>
          <span className="shrink-0" style={{ color: "var(--navy-900)" }}>
            <Icon name="shieldCheck" size={56} />
          </span>
          <div className="sm:border-l sm:pl-6" style={{ borderColor: "var(--border)" }}>
            <h3 className="font-bold" style={{ color: "var(--navy-900)", fontSize: "1.25rem" }}>
              {t("howOurRoleTitle")}
            </h3>
            <p className="mt-1" style={{ color: "var(--text)" }}>
              {t("howOurRoleBody")}
            </p>
          </div>
        </div>

        <div
          className="mt-6 grid grid-cols-1 items-center gap-6 p-6 sm:grid-cols-2 lg:grid-cols-5"
          style={{ ...panel, background: "var(--blue-50)" }}
        >
          <h3 className="font-bold" style={{ color: "var(--navy-900)", fontSize: "1.5rem" }}>
            {t("howBenefitsTitle")}
          </h3>
          {benefits.map((b) => (
            <div
              key={b.label}
              className="flex items-center gap-4 lg:border-l lg:pl-6"
              style={{ borderColor: "color-mix(in srgb, var(--blue-700) 25%, transparent)" }}
            >
              <span className="shrink-0" style={{ color: "var(--navy-900)" }}>
                <Icon name={b.icon} size={40} />
              </span>
              <span style={{ color: "var(--navy-900)", fontSize: "0.9375rem", lineHeight: 1.35 }}>{t(b.label)}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
