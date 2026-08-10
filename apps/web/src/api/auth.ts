import { apiGet, apiPost } from "./client";

export interface MeResponse {
  id: number;
  username: string;
  email: string;
  role: "admin" | "user";
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface RegisterRequest {
  username: string;
  email: string;
  password: string;
  role?: "admin" | "user";
}

export async function login(username: string, password: string): Promise<TokenResponse> {
  return apiPost<TokenResponse>("/auth/login", { username, password });
}

export async function register(body: RegisterRequest): Promise<unknown> {
  return apiPost("/auth/register", body);
}

export async function fetchMe(): Promise<MeResponse> {
  return apiGet<MeResponse>("/auth/me");
}
