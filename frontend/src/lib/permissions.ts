// Utilidades de permisos del cliente.
//
// IMPORTANTE: aquí NO se reimplementa la matriz rol → módulos. Esa decisión vive
// solo en el backend (`app/core/permissions.py`) y llega ya resuelta en
// `GET /auth/me` como `user.modules`. Este módulo únicamente interpreta ese mapa
// (¿alcanza el nivel?) y guarda las etiquetas de presentación.

import type {
  AccessLevel,
  EffectiveModules,
  ModuleKey,
  UserRole,
} from "@/lib/types/auth";

const RANK: Record<AccessLevel, number> = { read: 1, full: 2 };

/**
 * ¿Los módulos efectivos cubren `module` con al menos `level`?
 * `full` cubre `read`; un módulo ausente no cubre nada.
 */
export function canAccess(
  modules: EffectiveModules | undefined,
  module: ModuleKey,
  level: AccessLevel = "read",
): boolean {
  const granted = modules?.[module];
  return granted !== undefined && RANK[granted] >= RANK[level];
}

/** ¿El usuario tiene acceso de solo lectura (ve el módulo pero no puede editar)? */
export function isReadOnly(
  modules: EffectiveModules | undefined,
  module: ModuleKey,
): boolean {
  return canAccess(modules, module, "read") && !canAccess(modules, module, "full");
}

/** Etiqueta legible del rol (espejo de `ROLE_LABELS` del backend). */
export const ROLE_LABELS: Record<UserRole, string> = {
  admin: "Administrador",
  procesos: "Procesos",
  analista: "Analista",
  arquitecto: "Arquitecto",
  developer: "Developer",
  qa: "QA",
};

/** Etiqueta legible del módulo (espejo de `MODULE_LABELS` del backend). */
export const MODULE_LABELS: Record<ModuleKey, string> = {
  ef: "Agente EF",
  scrum: "Agente Scrum",
  arquitectura: "Agente Arquitectura",
  bd: "Agente Base de Datos",
  api: "Agente API",
  backend: "Agente Backend",
  frontend: "Agente Frontend",
  qa: "Agente QA",
  devops: "Agente DevOps",
  config: "Configuración",
};

export const LEVEL_LABELS: Record<AccessLevel, string> = {
  read: "Solo lectura",
  full: "Edición",
};

/** Todos los roles, en el orden en que se muestran en el panel. */
export const ALL_ROLES: UserRole[] = [
  "admin",
  "procesos",
  "analista",
  "arquitecto",
  "developer",
  "qa",
];

/** Todos los módulos, en orden de fase del ISDF. */
export const ALL_MODULES: ModuleKey[] = [
  "ef",
  "arquitectura",
  "bd",
  "api",
  "backend",
  "frontend",
  "qa",
  "scrum",
  "devops",
  "config",
];
