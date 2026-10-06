import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { login } from "../api/auth";
import { ApiError } from "../api/client";
import { useAuth } from "../contexts/AuthContext";
import { SocialButtons } from "./Register";

export function LoginPage() {
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
        <h1 className="mb-6 text-2xl font-semibold" style={{ color: "var(--navy-900)" }}>Sign in</h1>
        {error && <div className="mb-4 rounded-md px-3 py-2 text-sm" style={{ background: "var(--confid-bg)", color: "var(--confid-fg)", border: "1px solid var(--confid-fg)" }}>{error}</div>}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium">Email</label>
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
            <label className="mb-1 block text-sm font-medium">Password</label>
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
            {mutation.isPending ? "Signing in…" : "Sign in"}
          </button>
        </form>
        <div className="my-4 flex items-center gap-2 text-xs text-slate-400">
          <div className="h-px flex-1 bg-slate-200" />
          <span>or</span>
          <div className="h-px flex-1 bg-slate-200" />
        </div>
        <SocialButtons />
        <p className="mt-4 text-center text-sm" style={{ color: "var(--text-muted)" }}>
          No account?{" "}
          <Link to="/register" className="font-medium underline" style={{ color: "var(--blue-700)" }}>
            Register
          </Link>
        </p>
      </div>
    </div>
  );
}
