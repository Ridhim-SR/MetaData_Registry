import { useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  clearOAuthState,
  completeOAuthLogin,
  expectedOAuthState,
  type OAuthProvider,
} from "../api/auth";
import { ApiError } from "../api/client";
import { useAuth } from "../contexts/AuthContext";

/** Landing page for Google/Microsoft redirects: exchanges ?code= for our JWT. */
export function OAuthCallbackPage() {
  const { provider } = useParams<{ provider: string }>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { login: setAuth } = useAuth();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const run = async () => {
      if (provider !== "google" && provider !== "microsoft") {
        setError(`Unknown provider '${provider}'`);
        return;
      }
      const p = provider as OAuthProvider;
      const err = searchParams.get("error");
      if (err) {
        setError(searchParams.get("error_description") ?? `Sign-in cancelled (${err})`);
        return;
      }
      const code = searchParams.get("code");
      const state = searchParams.get("state");
      if (!code) {
        setError("Missing authorization code from provider");
        return;
      }
      const expected = expectedOAuthState(p);
      if (expected && state !== expected) {
        setError("State mismatch — please try signing in again");
        return;
      }
      try {
        const data = await completeOAuthLogin(p, code);
        clearOAuthState(p);
        setAuth(data.access_token);
        navigate("/", { replace: true });
      } catch (e) {
        setError(e instanceof ApiError ? e.detail : "Social sign-in failed");
      }
    };
    run();
  }, [provider, searchParams, navigate, setAuth]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-100">
      <div className="w-full max-w-sm rounded-lg bg-white p-8 text-center shadow">
        {error ? (
          <>
            <h1 className="mb-2 text-lg font-semibold text-red-700">Sign-in failed</h1>
            <p className="mb-4 text-sm text-slate-600">{error}</p>
            <button
              onClick={() => navigate("/login")}
              className="w-full rounded-md bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-700"
            >
              Back to sign in
            </button>
          </>
        ) : (
          <p className="text-sm text-slate-600">Completing sign-in…</p>
        )}
      </div>
    </div>
  );
}
