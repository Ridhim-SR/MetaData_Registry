import { Link, Outlet } from "react-router-dom";
import { t, useLanguage } from "../i18n";
import { RegistryHeader } from "./registry/RegistryHeader";
import { TopLoadingBar } from "./registry/TopLoadingBar";

export function RegistryLayout() {
  useLanguage();
  const year = new Date().getFullYear();
  const linkStyle: React.CSSProperties = {
    color: "#fff",
    fontSize: "0.875rem",
    textDecoration: "none",
  };

  return (
    <div
      className="flex min-h-screen flex-col"
      style={{ background: "var(--bg)", color: "var(--text)" }}
    >
      <RegistryHeader />
      <TopLoadingBar />
      <main id="main-content" className="flex-1" tabIndex={-1}>
        <Outlet />
      </main>
      <footer style={{ background: "var(--navy-900)", color: "#fff" }} aria-label={t("footerLabel")}>
        <div className="page-container mx-auto grid w-full max-w-7xl grid-cols-1 gap-6 px-4 py-8 sm:grid-cols-2 sm:px-6 md:grid-cols-4 lg:px-8">
          <div>
            <p className="font-bold" style={{ fontSize: "1rem" }}>
              {t("footerSiteName")}
            </p>
            <p style={{ fontSize: "0.875rem", color: "rgba(255,255,255,0.8)" }}>
              {t("govUP")}
            </p>
            <img
              src="/isb-logo.webp"
              alt={t("isbLogoAlt")}
              height={40}
              style={{
                marginTop: "0.75rem",
                height: 40,
                width: "auto",
                background: "#fff",
                borderRadius: 6,
                padding: "0.25rem 0.6rem",
              }}
              onError={(e) => {
                e.currentTarget.style.display = "none";
              }}
            />
          </div>
          <nav aria-label={t("footerLabel")}>
            <ul className="space-y-2">
              <li>
                <Link to="/about" style={linkStyle}>
                  {t("footerAbout")}
                </Link>
              </li>
              {/* Contact and Accessibility Statement hidden for now. */}
            </ul>
          </nav>
          <nav aria-label={t("footerLegal")}>
            <ul className="space-y-2">
              <li>
                <Link to="/copyrights" style={linkStyle}>
                  {t("footerTerms")}
                </Link>
              </li>
              <li>
                <Link to="/privacy" style={linkStyle}>
                  {t("footerPrivacy")}
                </Link>
              </li>
            </ul>
          </nav>
          <div style={{ fontSize: "0.875rem", color: "rgba(255,255,255,0.8)" }}>
            <p>{t("footerCopyright", { year })}</p>
          </div>
        </div>
      </footer>
    </div>
  );
}
