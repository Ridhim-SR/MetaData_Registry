import { useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { login } from "../api/auth";
import { ApiError } from "../api/client";
import { useAuth } from "../contexts/AuthContext";
import { t, useLanguage } from "../i18n";

export function LoginPage() {
  useLanguage();
  const { login: setAuth } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: { pathname?: string } })?.from?.pathname ?? "/";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () => login(email.trim(), password),
    onSuccess: (data) => {
      setAuth(data.access_token);
      navigate(from, { replace: true });
    },
    onError: (err: Error) => {
      setError(err instanceof ApiError ? err.detail : err.message);
    },
  });

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    mutation.mutate();
  };

  return (
    <div className="flex min-h-screen items-center justify-center" style={{ background: "var(--bg-alt)" }}>
      <div className="w-full max-w-sm p-8" style={{ background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 6 }}>
        <h1 className="mb-6 text-2xl font-semibold" style={{ color: "var(--navy-900)" }}>{t("signInLink")}</h1>
        {error && <div className="mb-4 rounded-md px-3 py-2 text-sm" style={{ background: "var(--confid-bg)", color: "var(--confid-fg)", border: "1px solid var(--confid-fg)" }}>{error}</div>}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium">{t("email")}</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
              className="w-full px-3 py-2 text-sm"
              style={{ border: "1px solid var(--border)", borderRadius: 6 }}
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">{t("password")}</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="current-password"
              className="w-full px-3 py-2 text-sm"
              style={{ border: "1px solid var(--border)", borderRadius: 6 }}
            />
          </div>
          <button
            type="submit"
            disabled={mutation.isPending}
            className="btn-primary w-full disabled:opacity-50"
          >
            {mutation.isPending ? t("signingIn") : t("signInLink")}
          </button>
        </form>
      </div>
    </div>
  );
}
