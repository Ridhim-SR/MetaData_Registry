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
import { t, useLanguage } from "../i18n";

/** Landing page for Google/Microsoft redirects: exchanges ?code= for our JWT. */
export function OAuthCallbackPage() {
  useLanguage();
  const { provider } = useParams<{ provider: string }>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { login: setAuth } = useAuth();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const run = async () => {
      if (provider !== "google" && provider !== "microsoft") {
        setError(t("oauthUnknownProvider", { provider: provider ?? "" }));
        return;
      }
      const p = provider as OAuthProvider;
      const err = searchParams.get("error");
      if (err) {
        setError(searchParams.get("error_description") ?? t("oauthCancelled", { err }));
        return;
      }
      const code = searchParams.get("code");
      const state = searchParams.get("state");
      if (!code) {
        setError(t("oauthMissingCode"));
        return;
      }
      const expected = expectedOAuthState(p);
      if (expected && state !== expected) {
        setError(t("oauthStateMismatch"));
        return;
      }
      try {
        const data = await completeOAuthLogin(p, code);
        clearOAuthState(p);
        setAuth(data.access_token);
        navigate("/", { replace: true });
      } catch (e) {
        setError(e instanceof ApiError ? e.detail : t("oauthFailed"));
      }
    };
    run();
  }, [provider, searchParams, navigate, setAuth]);

  return (
    <div className="flex min-h-screen items-center justify-center" style={{ background: "var(--bg-alt)" }}>
      <div className="w-full max-w-sm p-8 text-center" style={{ background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 6 }}>
        {error ? (
          <>
            <h1 className="mb-2 text-lg font-semibold" style={{ color: "var(--confid-fg)" }}>{t("signInFailed")}</h1>
            <p className="mb-4 text-sm" style={{ color: "var(--text-muted)" }}>{error}</p>
            <button
              onClick={() => navigate("/login")}
              className="btn-primary w-full"
            >
              {t("backToSignIn")}
            </button>
          </>
        ) : (
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>{t("completingSignIn")}</p>
        )}
      </div>
    </div>
  );
}
