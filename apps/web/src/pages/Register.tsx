import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { register } from "../api/auth";
import { ApiError } from "../api/client";

export function RegisterPage() {
  const navigate = useNavigate();
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () =>
      register({ first_name: firstName.trim(), last_name: lastName.trim(), email: email.trim(), password }),
    onSuccess: () => navigate("/login"),
    onError: (err: Error) => {
      setError(err instanceof ApiError ? err.detail : err.message);
    },
  });

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    mutation.mutate();
  };

  const inputClass =
    "w-full px-3 py-2 text-sm";

  const inputStyle: React.CSSProperties = { border: "1px solid var(--border)", borderRadius: 6 };

  return (
    <div className="flex min-h-screen items-center justify-center" style={{ background: "var(--bg-alt)" }}>
      <div className="w-full max-w-sm p-8" style={{ background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 6 }}>
        <h1 className="mb-6 text-2xl font-semibold" style={{ color: "var(--navy-900)" }}>Create account</h1>
        {error && <div className="mb-4 rounded-md px-3 py-2 text-sm" style={{ background: "var(--confid-bg)", color: "var(--confid-fg)", border: "1px solid var(--confid-fg)" }}>{error}</div>}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-700">First name</label>
              <input
                value={firstName}
                onChange={(e) => setFirstName(e.target.value)}
                required
                maxLength={100}
                autoComplete="given-name"
                className={inputClass}
                style={inputStyle}
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-700">Last name</label>
              <input
                value={lastName}
                onChange={(e) => setLastName(e.target.value)}
                required
                maxLength={100}
                autoComplete="family-name"
                className={inputClass}
                style={inputStyle}
              />
            </div>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
              className={inputClass}
              style={inputStyle}
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={6}
              autoComplete="new-password"
              className={inputClass}
              style={inputStyle}
            />
          </div>
          <button
            type="submit"
            disabled={mutation.isPending}
            className="btn-primary w-full disabled:opacity-50"
          >
            {mutation.isPending ? "Creating…" : "Register"}
          </button>
        </form>
        <p className="mt-4 text-center text-sm text-slate-600">
          Already registered?{" "}
          <Link to="/login" className="font-medium text-slate-900 underline">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
