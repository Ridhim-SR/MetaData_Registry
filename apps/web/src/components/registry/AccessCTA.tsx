import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { listDepartments } from "../../api/registry";
import { humanizeRaw } from "../../utils/format";
import { useAuth } from "../../contexts/AuthContext";

export function AccessCTA() {
  const { isAuthenticated, user } = useAuth();
  const departmentsQuery = useQuery({
    queryKey: ["registry-departments"],
    queryFn: listDepartments,
    enabled: isAuthenticated && Boolean(user?.department),
    retry: false,
    staleTime: 5 * 60 * 1000,
  });
  const deptDisplay =
    (departmentsQuery.data?.items ?? []).find((d) => d.slug === user?.department)?.display_name
    ?? (user?.department ? humanizeRaw(user.department) : undefined);

  return (
    <section
      aria-label="Get access"
      style={{ background: "var(--bg)" }}
    >
      <div className="mx-auto w-full max-w-3xl px-4 py-12 text-center sm:px-6">
        {isAuthenticated ? (
          <>
            <h2 className="font-semibold" style={{ color: "var(--navy-900)", fontSize: "1.375rem" }}>
              Explore your department&apos;s metadata
            </h2>
            <p className="mt-2 text-sm" style={{ color: "var(--text-muted)", fontSize: "0.9375rem" }}>
              {user?.department
                ? `Signed in${user.role === "admin" ? " as an administrator" : ` with the ${deptDisplay} department`}. Browse the catalog with your access applied.`
                : "Signed in. Browse the catalog with your access applied."}
            </p>
            <div className="mt-5">
              <Link
                to={user?.department ? `/departments/${encodeURIComponent(user.department)}` : "/explore"}
                className="btn-primary"
              >
                Go to My Department
              </Link>
            </div>
          </>
        ) : (
          <>
            <h2 className="font-semibold" style={{ color: "var(--navy-900)", fontSize: "1.375rem" }}>
              Need access to more data?
            </h2>
            <p className="mt-2 text-sm" style={{ color: "var(--text-muted)", fontSize: "0.9375rem" }}>
              Sign in with your department account to access department and restricted metadata.
            </p>
            <div className="mt-5">
              <Link to="/login" className="btn-primary">
                Sign In
              </Link>
            </div>
          </>
        )}
      </div>
    </section>
  );
}
