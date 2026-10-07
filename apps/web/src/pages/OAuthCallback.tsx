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
    <div className="flex min-h-screen items-center justify-center" style={{ background: "var(--bg-alt)" }}>
      <div className="w-full max-w-sm p-8 text-center" style={{ background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 6 }}>
        {error ? (
          <>
            <h1 className="mb-2 text-lg font-semibold" style={{ color: "var(--confid-fg)" }}>Sign-in failed</h1>
            <p className="mb-4 text-sm" style={{ color: "var(--text-muted)" }}>{error}</p>
            <button
              onClick={() => navigate("/login")}
              className="btn-primary w-full"
            >
              Back to sign in
            </button>
          </>
        ) : (
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>Completing sign-in…</p>
        )}
      </div>
    </div>
  );
}
