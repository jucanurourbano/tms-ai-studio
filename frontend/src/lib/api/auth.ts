// Funciones de la API de autenticación (cliente puro de FastAPI).

import type {
  AuthUser,
  LoginResult,
  RegisterInput,
  UserList,
} from "@/lib/types/auth";

import { apiRequest } from "./client";

const JSON_HEADERS = { "content-type": "application/json" };

export const authApi = {
  login(email: string, password: string): Promise<LoginResult> {
    return apiRequest<LoginResult>("/auth/login", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ email, password }),
    });
  },

  me(): Promise<AuthUser> {
    return apiRequest<AuthUser>("/auth/me");
  },

  register(input: RegisterInput): Promise<AuthUser> {
    return apiRequest<AuthUser>("/auth/register", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(input),
    });
  },

  listUsers(limit = 50, offset = 0): Promise<UserList> {
    return apiRequest<UserList>(`/auth/users?limit=${limit}&offset=${offset}`);
  },

  setActive(userId: string, isActive: boolean): Promise<AuthUser> {
    return apiRequest<AuthUser>(`/auth/users/${userId}`, {
      method: "PATCH",
      headers: JSON_HEADERS,
      body: JSON.stringify({ is_active: isActive }),
    });
  },
};
