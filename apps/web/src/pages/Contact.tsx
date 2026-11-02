import { Link } from "react-router-dom";
import { t, tNodes, useLanguage } from "../i18n";

export function ContactPage() {
  useLanguage();
  const catalogLink = (
    <Link to="/explore" className="underline" style={{ color: "var(--blue-700)" }}>
      {t("navCatalog")}
    </Link>
  );
  const dirLink = (
    <Link to="/departments" className="underline" style={{ color: "var(--blue-700)" }}>
      {t("deptDirTitle")}
    </Link>
  );
  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-10 sm:px-6">
      <Link to="/" className="mb-4 inline-block text-sm font-medium underline" style={{ color: "var(--blue-700)" }}>
        {t("backToHome")}
      </Link>
      <h1 className="font-bold" style={{ color: "var(--navy-900)", fontSize: "1.75rem" }}>{t("footerContact")}</h1>
      <div className="mt-4 space-y-4 text-sm leading-relaxed" style={{ color: "var(--text)", fontSize: "0.9375rem" }}>
        <p>{tNodes("contactP1", { catalogLink })}</p>
        <p>{tNodes("contactP2", { dirLink })}</p>
        <p>{t("contactP3")}</p>
      </div>
    </div>
  );
}
