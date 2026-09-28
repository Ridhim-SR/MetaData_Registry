import { apiGet, apiPost } from "./client";

export interface MeResponse {
  id: number;
  username: string;
  email: string;
  first_name: string | null;
  last_name: string | null;
  role: "admin" | "user";
  department: string | null;
  auth_provider: "local" | "google" | "microsoft";
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface RegisterRequest {
  first_name: string;
  last_name: string;
  email: string;
  password: string;
  department?: string;
}

export type OAuthProvider = "google" | "microsoft";

export async function login(email: string, password: string): Promise<TokenResponse> {
  return apiPost<TokenResponse>("/auth/login", { email, password });
}

export async function register(body: RegisterRequest): Promise<unknown> {
  return apiPost("/auth/register", body);
}

export async function fetchMe(): Promise<MeResponse> {
  return apiGet<MeResponse>("/auth/me");
}

export function oauthRedirectUri(provider: OAuthProvider): string {
  return `${window.location.origin}/auth/callback/${provider}`;
}

export async function getOAuthLoginUrl(provider: OAuthProvider): Promise<string> {
  const qs = new URLSearchParams({
    redirect_uri: oauthRedirectUri(provider),
    state: crypto.randomUUID(),
  });
  const data = await apiGet<{ authorization_url: string }>(
    `/auth/oauth/${provider}/login-url?${qs.toString()}`
  );
  sessionStorage.setItem(`oauth-state-${provider}`, qs.get("state") ?? "");
  return data.authorization_url;
}

export async function completeOAuthLogin(
  provider: OAuthProvider,
  code: string
): Promise<TokenResponse> {
  return apiPost<TokenResponse>(`/auth/oauth/${provider}/callback`, {
    code,
    redirect_uri: oauthRedirectUri(provider),
  });
}

export function expectedOAuthState(provider: OAuthProvider): string | null {
  return sessionStorage.getItem(`oauth-state-${provider}`);
}

export function clearOAuthState(provider: OAuthProvider): void {
  sessionStorage.removeItem(`oauth-state-${provider}`);
}

export function displayName(user: MeResponse | null | undefined): string {
  if (!user) return "";
  const full = [user.first_name, user.last_name].filter(Boolean).join(" ");
  return full || user.username;
}
