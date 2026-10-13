import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { displayName } from "../api/auth";
import { useAuth } from "../contexts/AuthContext";

const links = [
  { to: "/", label: "Home" },
  { to: "/dashboard", label: "Dashboard" },
  { to: "/explore", label: "Explore" },
  { to: "/ingestion", label: "Ingestion" },
  { to: "/users", label: "Users" },
];

export function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <div className="flex min-h-screen">
      <aside className="flex w-56 flex-col" style={{ borderRight: "1px solid var(--border)", background: "var(--bg-alt)" }}>
        <div className="px-4 py-4 text-lg font-semibold" style={{ borderBottom: "1px solid var(--border)", color: "var(--navy-900)" }}>Metadata Hub</div>
        <nav className="flex flex-1 flex-col gap-1 p-2">
          {links.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              className="rounded-md px-3 py-2 text-sm font-medium"
              style={({ isActive }) =>
                isActive
                  ? { background: "var(--navy-900)", color: "#fff" }
                  : { color: "var(--text)" }
              }
            >
              {link.label}
            </NavLink>
          ))}
        </nav>
        <div className="p-4" style={{ borderTop: "1px solid var(--border)" }}>
          <div className="mb-2 text-sm">
            <div className="font-medium">{displayName(user)}</div>
            <div className="text-xs" style={{ color: "var(--text-muted)" }}>
              {user?.email} · {user?.role}
            </div>
          </div>
          <button
            onClick={handleLogout}
            className="btn-primary w-full"
            style={{ fontSize: "0.875rem" }}
          >
            Log out
          </button>
        </div>
      </aside>
      <main className="flex-1 overflow-auto p-4 sm:p-6 lg:p-8">
        {/* Constrained container: keeps admin pages compact & centered on wide monitors */}
        <div className="page-container mx-auto w-full max-w-7xl">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
