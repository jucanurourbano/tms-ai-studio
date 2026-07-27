// Funciones de la API de autenticación (cliente puro de FastAPI).

import type {
  AuthUser,
  LoginResult,
  ModuleGrant,
  RegisterInput,
  RolesCatalog,
  UserList,
  UserRole,
} from "@/lib/types/auth";

import { apiRequest } from "./client";

const JSON_HEADERS = { "content-type": "application/json" };

export const authApi = {
  /** Chequeo público: ¿hay que crear la primera cuenta de administrador? */
  bootstrapStatus(): Promise<{ needs_bootstrap: boolean }> {
    return apiRequest<{ needs_bootstrap: boolean }>("/auth/bootstrap-status");
  },

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

  /** Cambia el rol funcional de un usuario (solo rol admin). */
  setRole(userId: string, role: UserRole): Promise<AuthUser> {
    return apiRequest<AuthUser>(`/auth/users/${userId}/role`, {
      method: "PATCH",
      headers: JSON_HEADERS,
      body: JSON.stringify({ role }),
    });
  },

  /**
   * Reemplaza los accesos adicionales de un usuario (solo rol admin).
   * Semántica de *replace*: lo que no venga en la lista se elimina.
   */
  setGrants(userId: string, grants: ModuleGrant[]): Promise<AuthUser> {
    return apiRequest<AuthUser>(`/auth/users/${userId}/grants`, {
      method: "PUT",
      headers: JSON_HEADERS,
      body: JSON.stringify({ grants }),
    });
  },

  /** Catálogo de roles/módulos/niveles con la matriz del backend. */
  roles(): Promise<RolesCatalog> {
    return apiRequest<RolesCatalog>("/auth/roles");
  },
};
