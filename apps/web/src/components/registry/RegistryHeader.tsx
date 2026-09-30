import { useState } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { displayName } from "../../api/auth";
import { useAuth } from "../../contexts/AuthContext";

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `rounded-md px-3 py-2 text-sm font-medium ${isActive ? "bg-slate-900 text-white" : "text-slate-700 hover:bg-slate-100"}`;

export function RegistryHeader() {
  const { user, isAuthenticated, logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);

  return (
    <header className="sticky top-0 z-40 border-b border-slate-200 bg-white/95 backdrop-blur">
      <div className="mx-auto flex h-16 w-full max-w-7xl items-center gap-4 px-4 sm:px-6 lg:px-8">
        <Link to="/" className="flex items-center gap-2" aria-label="SDA Metadata Registry home">
          <img src="/logo.jpg" alt="Uttar Pradesh government emblem" className="h-10 w-auto" />
          <span className="leading-tight">
            <span className="block text-base font-bold tracking-wide text-slate-900">
              SDA Metadata Registry
            </span>
            <span className="block text-[11px] font-semibold tracking-widest text-orange-700 uppercase">
              Government of Uttar Pradesh
            </span>
          </span>
        </Link>

        <nav aria-label="Primary" className="ml-4 hidden items-center gap-1 md:flex">
          <NavLink to="/explore" className={linkClass}>
            Search
          </NavLink>
          <NavLink to="/departments" className={linkClass}>
            Departments
          </NavLink>
        </nav>

        <div className="ml-auto flex items-center gap-2">
          {isAuthenticated ? (
            <div className="flex items-center gap-2">
              <div className="hidden text-right leading-tight sm:block">
                <div className="text-sm font-medium text-slate-900">{displayName(user)}</div>
                <div className="text-xs text-slate-500">
                  {user?.department ? `${user.department} · ` : ""}
                  {user?.role}
                </div>
              </div>
              <button
                onClick={() => navigate("/dashboard")}
                className="hidden rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-100 sm:block"
              >
                My Department
              </button>
              <button
                onClick={() => {
                  logout();
                  navigate("/");
                }}
                className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700"
              >
                Logout
              </button>
            </div>
          ) : (
            <button
              onClick={() => navigate("/login")}
              className="rounded-md bg-slate-900 px-4 py-1.5 text-sm font-medium text-white hover:bg-slate-700"
            >
              Login
            </button>
          )}
          <button
            className="rounded-md p-2 text-slate-600 hover:bg-slate-100 md:hidden"
            aria-expanded={open}
            aria-label="Toggle navigation"
            onClick={() => setOpen((v) => !v)}
          >
            <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 20 20" aria-hidden>
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
        <nav aria-label="Mobile" className="border-t border-slate-200 px-4 py-2 md:hidden">
          <NavLink to="/explore" className="block rounded-md px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100">
            Search
          </NavLink>
          <NavLink to="/departments" className="block rounded-md px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100">
            Departments
          </NavLink>
        </nav>
      )}
    </header>
  );
}
