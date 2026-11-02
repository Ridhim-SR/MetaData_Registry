import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { listDepartments } from "../../api/registry";
import { humanizeRaw } from "../../utils/format";
import { useAuth } from "../../contexts/AuthContext";
import { t, useLanguage } from "../../i18n";

export function AccessCTA() {
  useLanguage();
  const { isAuthenticated, user } = useAuth();
  const isAdmin = user?.role === "admin";
  const departmentsQuery = useQuery({
    queryKey: ["registry-departments"],
    queryFn: listDepartments,
    enabled: isAuthenticated && !isAdmin && Boolean(user?.department),
    retry: false,
    staleTime: 5 * 60 * 1000,
  });
  // Admin CTA hidden for now. The early return must stay below every hook:
  // returning before useQuery changes the hook count when the role changes.
  if (isAdmin) return null;
  const deptDisplay =
    (departmentsQuery.data?.items ?? []).find((d) => d.slug === user?.department)?.display_name
    ?? (user?.department ? humanizeRaw(user.department) : undefined);

  const userDept = user?.department ?? null;
  const hasDepartment = Boolean(userDept);

  return (
    <section
      aria-label={t("ctaAria")}
      style={{ background: "var(--bg)" }}
    >
      <div className="mx-auto w-full max-w-3xl px-4 py-12 text-center sm:px-6">
        {isAuthenticated ? (
          <>
            <h2 className="font-semibold" style={{ color: "var(--navy-900)", fontSize: "1.375rem" }}>
              {hasDepartment ? t("ctaMyDeptTitle") : t("ctaBrowseTitle")}
            </h2>
            <p className="mt-2 text-sm" style={{ color: "var(--text-muted)", fontSize: "0.9375rem" }}>
              {hasDepartment
                ? t("ctaSignedInDept", { dept: deptDisplay ?? "" })
                : t("ctaNoDept")}
            </p>
            <div className="mt-5">
              <Link
                to={userDept ? `/departments/${encodeURIComponent(userDept)}` : "/explore"}
                className="btn-primary"
              >
                {userDept ? t("ctaGoMyDept") : t("browseCatalog")}
              </Link>
            </div>
          </>
        ) : (
          <>
            <h2 className="font-semibold" style={{ color: "var(--navy-900)", fontSize: "1.375rem" }}>
              {t("ctaNeedAccess")}
            </h2>
            <p className="mt-2 text-sm" style={{ color: "var(--text-muted)", fontSize: "0.9375rem" }}>
              {t("ctaSignInBody")}
            </p>
            <div className="mt-5">
              <Link to="/login" className="btn-primary">
                {t("signIn")}
              </Link>
            </div>
          </>
        )}
      </div>
    </section>
  );
}
