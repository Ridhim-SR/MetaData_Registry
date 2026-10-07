import { useEffect, useRef, useState } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { displayName } from "../../api/auth";
import { useAuth } from "../../contexts/AuthContext";

const TEXT_SIZES = [0.875, 1, 1.125];
const POPULAR_DEPT_ICON = "🏛";

function useTextSize() {
  const [idx, setIdx] = useState(1);
  useEffect(() => {
    const saved = window.localStorage.getItem("sda-text-size");
    const n = saved ? Number(saved) : 1;
    if (TEXT_SIZES[n]) {
      setIdx(n);
      document.documentElement.style.fontSize = `${16 * TEXT_SIZES[n]}px`;
    }
  }, []);
  const set = (n: number) => {
    const clamped = Math.min(2, Math.max(0, n));
    setIdx(clamped);
    document.documentElement.style.fontSize = `${16 * TEXT_SIZES[clamped]}px`;
    window.localStorage.setItem("sda-text-size", String(clamped));
  };
  return { idx, set };
}

function useLanguage() {
  const [lang, setLang] = useState<"en" | "hi">("en");
  useEffect(() => {
    const saved = window.localStorage.getItem("sda-lang");
    if (saved === "hi") {
      setLang("hi");
      document.documentElement.lang = "hi";
    }
  }, []);
  const toggle = () => {
    const next = lang === "en" ? "hi" : "en";
    setLang(next);
    document.documentElement.lang = next === "hi" ? "hi" : "en";
    window.localStorage.setItem("sda-lang", next);
  };
  return { lang, toggle };
}

function navLinkStyle({ isActive }: { isActive: boolean }): React.CSSProperties {
  return {
    color: "#fff",
    textDecoration: "none",
    fontSize: "1rem",
    fontWeight: 500,
    padding: "0.6rem 0.9rem",
    borderBottom: isActive ? "3px solid var(--saffron)" : "3px solid transparent",
    display: "inline-block",
  };
}

export function RegistryHeader() {
  const { user, isAuthenticated, logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [headerQuery, setHeaderQuery] = useState("");
  const userMenuRef = useRef<HTMLDivElement>(null);
  const { idx, set } = useTextSize();
  const { lang, toggle } = useLanguage();
  // isAdmin NavLink hidden for now (see nav below); restore with the links.

  useEffect(() => {
    if (!userMenuOpen) return;
    const onDoc = (e: MouseEvent) => {
      if (userMenuRef.current && !userMenuRef.current.contains(e.target as Node)) {
        setUserMenuOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setUserMenuOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [userMenuOpen]);

  const handleLogout = () => {
    logout();
    setUserMenuOpen(false);
    navigate("/");
  };

  const submitHeaderSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const q = headerQuery.trim();
    setOpen(false);
    navigate(q ? `/explore?q=${encodeURIComponent(q)}` : "/explore");
  };

  return (
    <>
      {/* 1. Utility bar */}
      <div style={{ background: "var(--bg-alt)", borderBottom: "1px solid var(--border)" }}>
        <div
          className="mx-auto flex w-full max-w-7xl flex-wrap items-center gap-2 px-4 py-1 sm:px-6 lg:px-8"
          style={{ fontSize: "0.8125rem" }}
        >
          <a href="#main-content" className="skip-link">
            Skip to main content
          </a>
          <span style={{ color: "var(--text-muted)" }} aria-hidden>
            {POPULAR_DEPT_ICON} Uttar Pradesh Government Portal
          </span>
          <div className="ml-auto flex items-center gap-1" role="group" aria-label="Text size">
            <button
              type="button"
              onClick={() => set(idx - 1)}
              aria-label="Decrease text size"
              style={{
                border: "1px solid var(--border)",
                borderRadius: 6,
                background: "var(--bg)",
                color: "var(--text)",
                padding: "0.1rem 0.5rem",
                fontSize: "0.8125rem",
                cursor: "pointer",
              }}
            >
              A-
            </button>
            <button
              type="button"
              onClick={() => set(1)}
              aria-label="Reset text size"
              style={{
                border: "1px solid var(--border)",
                borderRadius: 6,
                background: idx === 1 ? "var(--blue-50)" : "var(--bg)",
                color: "var(--text)",
                padding: "0.1rem 0.5rem",
                fontSize: "0.8125rem",
                cursor: "pointer",
              }}
            >
              A
            </button>
            <button
              type="button"
              onClick={() => set(idx + 1)}
              aria-label="Increase text size"
              style={{
                border: "1px solid var(--border)",
                borderRadius: 6,
                background: "var(--bg)",
                color: "var(--text)",
                padding: "0.1rem 0.5rem",
                fontSize: "0.8125rem",
                cursor: "pointer",
              }}
            >
              A+
            </button>
          </div>
          <button
            type="button"
            onClick={toggle}
            aria-label="Toggle language between English and Hindi"
            style={{
              border: "1px solid var(--border)",
              borderRadius: 6,
              background: "var(--bg)",
              color: "var(--blue-700)",
              padding: "0.1rem 0.6rem",
              fontSize: "0.8125rem",
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            {lang === "en" ? "English / हिन्दी" : "हिन्दी / English"}
          </button>
        </div>
      </div>

      {/* 2. Saffron strip */}
      <div aria-hidden style={{ height: 3, background: "var(--saffron)" }} />

      {/* 3. Header (white) */}
      <header style={{ background: "var(--bg)" }}>
        <div className="mx-auto flex w-full max-w-7xl items-center gap-3 px-4 py-3 sm:px-6 lg:px-8">
          <Link
            to="/"
            className="flex items-center gap-3"
            aria-label="SDA Metadata Registry home"
            style={{ textDecoration: "none" }}
          >
            <img
              src="/logo.jpg"
              alt="State emblem of Uttar Pradesh"
              className="h-12 w-auto"
              style={{ height: 48 }}
            />
            <span className="leading-tight">
              <span
                className="block font-bold"
                style={{ color: "var(--navy-900)", fontSize: "1.25rem" }}
              >
                Metadata Registry
              </span>
              <span
                className="block font-medium"
                style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}
              >
                Government of Uttar Pradesh
              </span>
            </span>
          </Link>
          <form
            onSubmit={submitHeaderSearch}
            role="search"
            aria-label="Site search"
            className="ml-auto hidden min-w-0 flex-1 items-center gap-2 md:flex"
            style={{ maxWidth: 420 }}
          >
            <label htmlFor="header-search" className="sr-only">
              Search datasets and departments
            </label>
            <input
              id="header-search"
              type="search"
              value={headerQuery}
              onChange={(e) => setHeaderQuery(e.target.value)}
              placeholder="Search datasets, departments…"
              autoComplete="off"
              style={{
                flex: 1,
                minWidth: 0,
                border: "1px solid var(--border)",
                borderRadius: 6,
                padding: "0.45rem 0.75rem",
                fontSize: "0.9375rem",
                color: "var(--text)",
                background: "var(--bg)",
              }}
            />
            <button type="submit" className="btn-primary" style={{ padding: "0.45rem 1rem", fontSize: "0.9375rem" }}>
              Search
            </button>
          </form>
        </div>
      </header>

      {/* 4. Navy nav bar */}
      <div style={{ background: "var(--navy-900)" }}>
        <div className="mx-auto flex w-full max-w-7xl items-center px-4 sm:px-6 lg:px-8">
          <nav aria-label="Primary" className="hidden items-center md:flex">
            <NavLink to="/" end style={navLinkStyle}>
              Home
            </NavLink>
            <NavLink to="/explore" end style={navLinkStyle}>
              Catalog
            </NavLink>
            <NavLink to="/departments" style={navLinkStyle}>
              Departments
            </NavLink>
            {/* Hidden for now: My Requests (/dashboard) and Admin (/users).
                Re-enable by restoring the authenticated NavLinks below.
            {isAuthenticated && (
              <NavLink to="/dashboard" style={navLinkStyle}>
                My Requests
              </NavLink>
            )}
            {isAuthenticated && isAdmin && (
              <NavLink to="/users" style={navLinkStyle}>
                Admin
              </NavLink>
            )} */}
          </nav>

          <div className="ml-auto flex items-center gap-2 py-1.5">
            {isAuthenticated ? (
              <div className="relative hidden sm:block" ref={userMenuRef}>
                <button
                  type="button"
                  className="btn-nav-outline"
                  aria-haspopup="menu"
                  aria-expanded={userMenuOpen}
                  onClick={() => setUserMenuOpen((v) => !v)}
                >
                  {displayName(user) || "Account"} ▾
                </button>
                {userMenuOpen && (
                  <div
                    role="menu"
                    aria-label="User menu"
                    style={{
                      position: "absolute",
                      right: 0,
                      top: "calc(100% + 6px)",
                      minWidth: 220,
                      background: "var(--bg)",
                      border: "1px solid var(--border)",
                      borderRadius: 6,
                      zIndex: 50,
                    }}
                  >
                    <div
                      className="px-4 py-2"
                      style={{ borderBottom: "1px solid var(--border)", fontSize: "0.875rem" }}
                    >
                      <div style={{ color: "var(--text)", fontWeight: 600 }}>
                        {displayName(user)}
                      </div>
                      <div style={{ color: "var(--text-muted)", fontSize: "0.8125rem" }}>
                        {user?.department ? `${user.department} · ` : ""}
                        {user?.role}
                      </div>
                    </div>
                    <button
                      type="button"
                      role="menuitem"
                      onClick={handleLogout}
                      style={{
                        display: "block",
                        width: "100%",
                        textAlign: "left",
                        background: "none",
                        border: "none",
                        padding: "0.6rem 1rem",
                        fontSize: "0.875rem",
                        color: "var(--text)",
                        cursor: "pointer",
                      }}
                    >
                      Logout
                    </button>
                  </div>
                )}
              </div>
            ) : (
              <button onClick={() => navigate("/login")} className="btn-nav-outline hidden sm:inline-flex">
                Login
              </button>
            )}
            <button
              className="rounded-md p-2 md:hidden"
              style={{ color: "#fff" }}
              aria-expanded={open}
              aria-label="Toggle navigation menu"
              onClick={() => setOpen((v) => !v)}
            >
              <svg className="h-6 w-6" fill="currentColor" viewBox="0 0 20 20" aria-hidden>
                <path
                  fillRule="evenodd"
                  d="M3 5a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zM3 10a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zM3 15a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1z"
                  clipRule="evenodd"
                />
              </svg>
            </button>
          </div>
        </div>
        {open && (
          <nav
            aria-label="Mobile"
            className="border-t px-4 py-2 md:hidden"
            style={{ borderColor: "rgba(255,255,255,0.2)" }}
          >
            {[
              { to: "/", label: "Home" },
              { to: "/explore", label: "Catalog" },
              { to: "/departments", label: "Departments" },
              // Hidden for now: My Requests (/dashboard) and Admin (/users).
            ].map((l) => (
              <NavLink
                key={l.label + l.to}
                to={l.to}
                onClick={() => setOpen(false)}
                className="block rounded-md px-3 py-2"
                style={{ color: "#fff", fontSize: "1rem", textDecoration: "none" }}
              >
                {l.label}
              </NavLink>
            ))}
            <form onSubmit={submitHeaderSearch} role="search" aria-label="Site search" className="mt-2 flex gap-2">
              <label htmlFor="header-search-mobile" className="sr-only">
                Search datasets and departments
              </label>
              <input
                id="header-search-mobile"
                type="search"
                value={headerQuery}
                onChange={(e) => setHeaderQuery(e.target.value)}
                placeholder="Search datasets, departments…"
                autoComplete="off"
                style={{
                  flex: 1,
                  minWidth: 0,
                  border: "1px solid rgba(255,255,255,0.4)",
                  borderRadius: 6,
                  padding: "0.45rem 0.75rem",
                  fontSize: "1rem",
                  color: "#fff",
                  background: "rgba(255,255,255,0.12)",
                }}
              />
              <button type="submit" className="btn-nav-outline">
                Search
              </button>
            </form>
            {isAuthenticated ? (
              <button onClick={handleLogout} className="btn-nav-outline mt-2">
                Logout ({displayName(user)})
              </button>
            ) : (
              <button onClick={() => navigate("/login")} className="btn-nav-outline mt-2">
                Login
              </button>
            )}
          </nav>
        )}
      </div>
    </>
  );
}
