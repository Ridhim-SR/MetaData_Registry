import { Link } from "react-router-dom";
import { t, useLanguage } from "../i18n";

export function PrivacyPolicyPage() {
  useLanguage();
  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-10 sm:px-6">
      <Link to="/" className="mb-4 inline-block text-sm font-medium underline" style={{ color: "var(--blue-700)" }}>
        {t("backToHome")}
      </Link>
      <h1 className="text-2xl font-bold" style={{ color: "var(--navy-900)" }}>{t("privacyTitle")}</h1>
      <p className="mt-4 text-sm leading-relaxed" style={{ color: "var(--text)" }}>
        {t("privacyBody")}
      </p>
    </div>
  );
}
