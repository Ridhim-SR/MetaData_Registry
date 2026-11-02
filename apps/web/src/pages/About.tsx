import { Link } from "react-router-dom";
import { t, tNodes, useLanguage } from "../i18n";

export function AboutPage() {
  useLanguage();
  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-10 sm:px-6">
      <Link to="/" className="mb-4 inline-block text-sm font-medium underline" style={{ color: "var(--blue-700)" }}>
        {t("backToHome")}
      </Link>
      <h1 className="font-bold" style={{ color: "var(--navy-900)", fontSize: "1.75rem" }}>{t("footerAbout")}</h1>
      <div className="mt-4 space-y-4 text-sm leading-relaxed" style={{ color: "var(--text)", fontSize: "0.9375rem" }}>
        <p>{t("aboutP1")}</p>
        <p>{t("aboutP2")}</p>
        <p>
          {tNodes("aboutP3", {
            dirLink: (
              <Link to="/departments" className="underline" style={{ color: "var(--blue-700)" }}>
                {t("deptDirTitle")}
              </Link>
            ),
            catalogLink: (
              <Link to="/explore" className="underline" style={{ color: "var(--blue-700)" }}>
                {t("navCatalog")}
              </Link>
            ),
          })}
        </p>
      </div>
    </div>
  );
}
