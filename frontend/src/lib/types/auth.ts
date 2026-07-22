// Tipos de autenticación (espejo de los esquemas del backend).

export type UserRole = "admin" | "member";

export interface AuthUser {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  created_at?: string | null;
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
