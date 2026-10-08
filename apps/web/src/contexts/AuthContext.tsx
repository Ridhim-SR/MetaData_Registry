import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchMe, type MeResponse } from "../api/auth";
import { getToken, setToken } from "../api/client";

interface AuthContextValue {
  user: MeResponse | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (token: string) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export const UNAUTHORIZED_EVENT = "sda:unauthorized";

/** True when the JWT carries an exp claim that is already past. */
export function isTokenExpired(token: string | null): boolean {
  if (!token) return false;
  try {
    const payload = JSON.parse(atob(token.split(".")[1] ?? ""));
    return typeof payload.exp === "number" && payload.exp * 1000 <= Date.now();
  } catch {
    return false;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [token, setTokenState] = useState<string | null>(() => getToken());

  const logout = useMemo(() => {
    return () => {
      setToken(null);
      setTokenState(null);
    };
  }, []);

  // Proactive: drop the session as soon as the token clock says expired —
  // on mount, every 30s, and whenever the tab regains focus.
  useEffect(() => {
    const check = () => {
      const current = getToken();
      if (current && isTokenExpired(current)) {
        setToken(null);
        setTokenState(null);
      }
    };
    check();
    const timer = window.setInterval(check, 30_000);
    window.addEventListener("focus", check);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("focus", check);
    };
  }, []);

  // Reactive: any API 401 clears storage first (see api/client.ts) and
  // notifies here so in-memory state follows immediately.
  useEffect(() => {
    const onUnauthorized = () => {
      setTokenState(null);
      queryClient.removeQueries({ queryKey: ["me"] });
    };
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
  }, [queryClient]);

  const { data: user, isLoading } = useQuery({
    queryKey: ["me"],
    queryFn: fetchMe,
    enabled: Boolean(token),
    retry: false,
    staleTime: 5 * 60 * 1000,
  });

  useEffect(() => {
    if (!token) {
      queryClient.removeQueries({ queryKey: ["me"] });
    }
  }, [token, queryClient]);

  const value = useMemo<AuthContextValue>(
    () => ({
      user: user ?? null,
      isAuthenticated: Boolean(token),
      isLoading,
      login: (newToken: string) => {
        setToken(newToken);
        setTokenState(newToken);
      },
      logout,
    }),
    [user, token, isLoading, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
