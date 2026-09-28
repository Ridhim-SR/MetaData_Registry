import { apiGet } from "./client";

export interface UserOut {
  id: number;
  username: string;
  email: string;
  first_name: string | null;
  last_name: string | null;
  role: "admin" | "user";
  department: string | null;
  auth_provider: "local" | "google" | "microsoft";
  created_at: string;
  updated_at: string;
}

export async function fetchUsers(): Promise<UserOut[]> {
  return apiGet<UserOut[]>("/users");
}
