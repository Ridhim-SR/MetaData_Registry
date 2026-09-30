import { Link } from "react-router-dom";
import { useAuth } from "../../contexts/AuthContext";

export function AccessCTA() {
  const { isAuthenticated, user } = useAuth();

  return (
    <section aria-label="Get access" className="mx-auto w-full max-w-3xl px-4 py-12 text-center sm:px-6">
      {isAuthenticated ? (
        <>
          <h2 className="text-xl font-semibold text-slate-900">Explore your department&apos;s metadata</h2>
          <p className="mt-2 text-sm text-slate-600">
            {user?.department
              ? `Signed in${user.role === "admin" ? " as an administrator" : ` with the ${user.department} department`}. Browse the catalog with your access applied.`
              : "Signed in. Browse the catalog with your access applied."}
          </p>
          <div className="mt-5">
            <Link
              to={user?.department ? `/explore?department=${encodeURIComponent(user.department)}` : "/explore"}
              className="inline-flex rounded-full bg-slate-900 px-6 py-2.5 text-sm font-medium text-white hover:bg-slate-700"
            >
              Go to My Department
            </Link>
          </div>
        </>
      ) : (
        <>
          <h2 className="text-xl font-semibold text-slate-900">Need access to more data?</h2>
          <p className="mt-2 text-sm text-slate-600">
            Sign in with your department account to access department and restricted metadata.
          </p>
          <div className="mt-5">
            <Link
              to="/login"
              className="inline-flex rounded-full bg-slate-900 px-6 py-2.5 text-sm font-medium text-white hover:bg-slate-700"
            >
              Sign In
            </Link>
          </div>
        </>
      )}
    </section>
  );
}
