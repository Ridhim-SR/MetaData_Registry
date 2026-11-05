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
  const headingStyle: React.CSSProperties = { fontWeight: 700, fontSize: "1rem", lineHeight: 1.5, color: "#fff" };

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
        {/* Every column starts with a heading of the same size, so their first lines align. */}
        <div className="page-container mx-auto grid w-full max-w-7xl grid-cols-1 gap-8 px-4 pt-10 pb-8 sm:grid-cols-2 sm:px-6 md:grid-cols-[2fr_1fr_1fr] lg:px-8">
          <div>
            <p style={headingStyle}>{t("footerSiteName")}</p>
            <p className="mt-1" style={{ fontSize: "0.875rem", color: "rgba(255,255,255,0.8)" }}>
              {t("govUP")}
            </p>
            <img
              src="/isb-logo.webp"
              alt={t("isbLogoAlt")}
              height={40}
              style={{
                marginTop: "1rem",
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
          <nav aria-labelledby="footer-info">
            <p id="footer-info" style={headingStyle}>
              {t("footerInfo")}
            </p>
            <ul className="mt-3 space-y-2">
              <li>
                <Link to="/about" style={linkStyle}>
                  {t("footerAbout")}
                </Link>
              </li>
              <li>
                <Link to="/disclaimer" style={linkStyle}>
                  {t("footerDisclaimer")}
                </Link>
              </li>
              {/* Contact and Accessibility Statement hidden for now. */}
            </ul>
          </nav>
          <nav aria-labelledby="footer-legal">
            <p id="footer-legal" style={headingStyle}>
              {t("footerLegal")}
            </p>
            <ul className="mt-3 space-y-2">
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
        </div>
        <div style={{ borderTop: "1px solid rgba(255,255,255,0.15)" }}>
          <p
            className="page-container mx-auto w-full max-w-7xl px-4 py-4 sm:px-6 lg:px-8"
            style={{ fontSize: "0.8125rem", color: "rgba(255,255,255,0.75)" }}
          >
            {t("footerCopyright", { year })}
          </p>
        </div>
      </footer>
    </div>
  );
}
