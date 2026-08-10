import { apiGet } from "./client";

export interface UserOut {
  id: number;
  username: string;
  email: string;
  role: "admin" | "user";
  created_at: string;
  updated_at: string;
}

export async function fetchUsers(): Promise<UserOut[]> {
  return apiGet<UserOut[]>("/users");
}
