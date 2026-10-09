import { Link, Outlet } from "react-router-dom";
import { RegistryHeader } from "./registry/RegistryHeader";
import { TopLoadingBar } from "./registry/TopLoadingBar";

export function RegistryLayout() {
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
      <footer style={{ background: "var(--navy-900)", color: "#fff" }} aria-label="Footer">
        <div className="page-container mx-auto grid w-full max-w-7xl grid-cols-1 gap-6 px-4 py-8 sm:grid-cols-2 sm:px-6 md:grid-cols-4 lg:px-8">
          <div>
            <p className="font-bold" style={{ fontSize: "1rem" }}>
              SDA Metadata Registry
            </p>
            <p style={{ fontSize: "0.875rem", color: "rgba(255,255,255,0.8)" }}>
              Government of Uttar Pradesh
            </p>
            <img
              src="/isb-logo.webp"
              alt="ISB Bharti Institute of Public Policy"
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
          <nav aria-label="Footer">
            <ul className="space-y-2">
              <li>
                <Link to="/about" style={linkStyle}>
                  About
                </Link>
              </li>
              <li>
                <Link to="/contact" style={linkStyle}>
                  Contact
                </Link>
              </li>
              <li>
                <Link to="/privacy" style={linkStyle}>
                  Accessibility Statement
                </Link>
              </li>
            </ul>
          </nav>
          <nav aria-label="Legal">
            <ul className="space-y-2">
              <li>
                <Link to="/copyrights" style={linkStyle}>
                  Terms
                </Link>
              </li>
              <li>
                <Link to="/privacy" style={linkStyle}>
                  Privacy
                </Link>
              </li>
            </ul>
          </nav>
          <div style={{ fontSize: "0.875rem", color: "rgba(255,255,255,0.8)" }}>
            <p>© {year} SDA Metadata Registry. All rights reserved.</p>
          </div>
        </div>
      </footer>
    </div>
  );
}
