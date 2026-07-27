// Tipos de autenticación y permisos (espejo de los esquemas del backend).
// La matriz rol → módulos vive SOLO en el backend (`app/core/permissions.py`);
// aquí se consumen los módulos ya resueltos que envía `GET /auth/me`.

/** Roles funcionales por fase del ISDF. */
export type UserRole =
  | "admin"
  | "procesos"
  | "analista"
  | "arquitecto"
  | "developer"
  | "qa";

/** Módulos protegibles: un agente del ISDF, o la configuración. */
export type ModuleKey =
  | "ef"
  | "scrum"
  | "arquitectura"
  | "bd"
  | "api"
  | "backend"
  | "frontend"
  | "qa"
  | "devops"
  | "config";

/** Nivel de acceso a un módulo. `full` implica `read`. */
export type AccessLevel = "read" | "full";

/** Acceso adicional explícito concedido a un usuario. */
export interface ModuleGrant {
  module: ModuleKey;
  level: AccessLevel;
}

/**
 * Módulos efectivos: rol + accesos adicionales, ya resueltos por el backend.
 * Un módulo ausente significa "sin acceso de ningún tipo".
 */
export type EffectiveModules = Partial<Record<ModuleKey, AccessLevel>>;

export interface AuthUser {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  created_at?: string | null;
  grants: ModuleGrant[];
  modules: EffectiveModules;
}

export interface LoginResult {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
  user: AuthUser;
}

export interface UserList {
  total: number;
  limit: number;
  offset: number;
  items: AuthUser[];
}

export interface RegisterInput {
  email: string;
  full_name: string;
  password: string;
  role: UserRole;
}

/** Catálogo de `GET /auth/roles`: la matriz del backend, para el panel. */
export interface RolesCatalog {
  roles: {
    value: UserRole;
    label: string;
    modules: Record<string, AccessLevel>;
  }[];
  modules: { value: ModuleKey; label: string }[];
  levels: AccessLevel[];
}
