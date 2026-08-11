// Mapa ruta → permiso exigido. Lo consume `AppGate` para cortar el acceso por
// URL directa: sin el permiso, redirige al dashboard con un aviso.
//
// El backend protege igualmente cada endpoint (`require_module`): esto es
// usabilidad, no seguridad. Aunque alguien saltara esta guarda, la API
// respondería 403.

import type { AccessLevel, ModuleKey } from "@/lib/types/auth";

export interface RouteRule {
  /** Prefijo de ruta (coincide con la ruta exacta o con `prefijo/...`). */
  prefix: string;
  module: ModuleKey;
  /** Nivel exigido. Las rutas de creación exigen `full`. */
  level: AccessLevel;
}

// Orden importante: se evalúa la PRIMERA regla que coincide, así que las rutas
// más específicas (p. ej. `/agents/ef/new`, que exige edición) van antes.
export const ROUTE_RULES: RouteRule[] = [
  { prefix: "/agents/ef/new", module: "ef", level: "full" },
  { prefix: "/agents/ef", module: "ef", level: "read" },
  { prefix: "/agents/scrum/new", module: "scrum", level: "full" },
  { prefix: "/agents/scrum", module: "scrum", level: "read" },
  { prefix: "/agents/arquitectura/new", module: "arquitectura", level: "full" },
  { prefix: "/agents/arquitectura", module: "arquitectura", level: "read" },
  { prefix: "/agents/bd/new", module: "bd", level: "full" },
  { prefix: "/agents/bd", module: "bd", level: "read" },
  { prefix: "/agents/api/new", module: "api", level: "full" },
  { prefix: "/agents/api", module: "api", level: "read" },
  // El inventario lo consulta todo el mundo; escribir se decide por endpoint.
  { prefix: "/inventario", module: "inventario", level: "read" },
  { prefix: "/configuracion", module: "config", level: "read" },
];

/** Regla aplicable a una ruta, o `null` si es libre (p. ej. el dashboard). */
export function ruleFor(pathname: string): RouteRule | null {
  return (
    ROUTE_RULES.find(
      (rule) =>
        pathname === rule.prefix || pathname.startsWith(`${rule.prefix}/`),
    ) ?? null
  );
}
