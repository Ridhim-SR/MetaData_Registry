import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { listDepartments } from "../../api/registry";
import { humanizeRaw } from "../../utils/format";
import { useAuth } from "../../contexts/AuthContext";

export function AccessCTA() {
  const { isAuthenticated, user } = useAuth();
  const isAdmin = user?.role === "admin";
  // Admin CTA hidden for now; the block below is kept for later re-use.
  if (isAdmin) return null;
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

  const userDept = user?.department ?? null;
  const hasDepartment = Boolean(userDept);

  return (
    <section
      aria-label="Get access"
      style={{ background: "var(--bg)" }}
    >
      <div className="mx-auto w-full max-w-3xl px-4 py-12 text-center sm:px-6">
        {isAuthenticated ? (
          <>
            <h2 className="font-semibold" style={{ color: "var(--navy-900)", fontSize: "1.375rem" }}>
              {hasDepartment ? "Explore your department's metadata" : "Browse the catalog"}
            </h2>
            <p className="mt-2 text-sm" style={{ color: "var(--text-muted)", fontSize: "0.9375rem" }}>
              {hasDepartment
                ? `Signed in with the ${deptDisplay} department. Browse the catalog with your access applied.`
                : "Your account has no department assigned, so department datasets stay hidden. Ask your administrator to assign your department, or browse public datasets below."}
            </p>
            <div className="mt-5">
              <Link
                to={userDept ? `/departments/${encodeURIComponent(userDept)}` : "/explore"}
                className="btn-primary"
              >
                {userDept ? "Go to My Department" : "Browse Catalog"}
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
