// Navegación por fases del ISDF. Los agentes EF (ESPECIFICAR), Arquitectura y BD
// (DISEÑAR) y Scrum (GESTIONAR) están activos; los demás se muestran visibles pero
// deshabilitados ("próximamente").
//
// Los iconos se referencian por clave (string) y se resuelven a componentes lucide
// en la sidebar, para mantener este módulo libre de dependencias de UI.

import { canAccess } from "@/lib/permissions";
import type { EffectiveModules, ModuleKey } from "@/lib/types/auth";

export type AgentIcon =
  | "file-search"
  | "kanban"
  | "layers"
  | "database"
  | "plug"
  | "server"
  | "monitor"
  | "shield-check"
  | "rocket";

export interface AgentNav {
  key: string;
  name: string;
  /**
   * Módulo de permisos al que pertenece (ver `lib/permissions.ts`). La sidebar y
   * el dashboard solo muestran los agentes cuyo módulo el usuario puede ver.
   */
  module: ModuleKey;
  href?: string;
  enabled: boolean;
  icon: AgentIcon;
  /** Descripción corta de qué hace el agente (dashboard). */
  description?: string;
}

export interface PhaseNav {
  /** Clave estable para persistir el estado plegado/expandido. */
  key: string;
  phase: string;
  agents: AgentNav[];
}

export const ISDF_NAV: PhaseNav[] = [
  {
    key: "especificar",
    phase: "Especificar",
    agents: [
      {
        key: "ef",
        module: "ef",
        name: "Agente EF",
        href: "/agents/ef",
        enabled: true,
        icon: "file-search",
        description:
          "Traduce Procesos a lenguaje de Sistemas: requisitos, modelo de datos y preguntas de afinamiento, con trazabilidad a la evidencia.",
      },
    ],
  },
  {
    key: "disenar",
    phase: "Diseñar",
    agents: [
      {
        key: "arquitectura",
        module: "arquitectura",
        name: "Arquitectura",
        href: "/agents/arquitectura",
        enabled: true,
        icon: "layers",
        description:
          "Define la arquitectura técnica de la solución a partir de la EF y el plan ágil.",
      },
      {
        key: "bd",
        module: "bd",
        name: "Base de Datos",
        href: "/agents/bd",
        enabled: true,
        icon: "database",
        description:
          "Diseña el modelo de datos físico y genera el DDL desde una arquitectura lista.",
      },
    ],
  },
  {
    key: "construir",
    phase: "Construir",
    agents: [
      {
        key: "api",
        module: "api",
        name: "API",
        href: "/agents/api",
        enabled: true,
        icon: "plug",
        description: "Especifica los contratos de API: endpoints y payloads.",
      },
      {
        key: "backend",
        module: "backend",
        name: "Backend",
        enabled: false,
        icon: "server",
        description: "Genera la capa de servicios y la lógica de negocio.",
      },
      {
        key: "frontend",
        module: "frontend",
        name: "Frontend",
        enabled: false,
        icon: "monitor",
        description: "Construye la interfaz de usuario de la solución.",
      },
    ],
  },
  {
    key: "verificar",
    phase: "Verificar",
    agents: [
      {
        key: "qa",
        module: "qa",
        name: "QA",
        enabled: false,
        icon: "shield-check",
        description: "Diseña casos de prueba y valida la calidad del entregable.",
      },
    ],
  },
  {
    key: "gestionar",
    phase: "Gestionar",
    agents: [
      {
        key: "scrum",
        module: "scrum",
        name: "Agente Scrum",
        href: "/agents/scrum",
        enabled: true,
        icon: "kanban",
        description:
          "Genera épicas, historias, criterios, estimaciones y plan de sprints desde una EF lista.",
      },
      {
        key: "devops",
        module: "devops",
        name: "DevOps",
        enabled: false,
        icon: "rocket",
        description: "Automatiza el despliegue y la integración continua.",
      },
    ],
  },
];

/** Un agente con la fase ISDF a la que pertenece (aplanado para el dashboard). */
export interface FlatAgent extends AgentNav {
  phase: string;
}

/** Aplana `ISDF_NAV` a una única lista de agentes, con su fase, en orden ISDF. */
export function flatAgents(): FlatAgent[] {
  return ISDF_NAV.flatMap((p) =>
    p.agents.map((a) => ({ ...a, phase: p.phase })),
  );
}

/**
 * Navegación filtrada por permisos: solo las fases y agentes cuyo módulo el
 * usuario puede al menos LEER. Los módulos sin acceso quedan **invisibles**, no
 * deshabilitados; una fase sin agentes visibles desaparece entera.
 *
 * Ojo: "visible" y "activo" son cosas distintas. Un developer ve API/Backend/
 * Frontend porque tiene permiso, y siguen mostrándose como "pronto" mientras el
 * agente no exista (`enabled: false`).
 */
export function navForModules(modules: EffectiveModules): PhaseNav[] {
  return ISDF_NAV.map((phase) => ({
    ...phase,
    agents: phase.agents.filter((a) => canAccess(modules, a.module)),
  })).filter((phase) => phase.agents.length > 0);
}

/** Agentes visibles para esos permisos, aplanados (dashboard). */
export function flatAgentsForModules(modules: EffectiveModules): FlatAgent[] {
  return navForModules(modules).flatMap((p) =>
    p.agents.map((a) => ({ ...a, phase: p.phase })),
  );
}

/** Un grupo tiene al menos un agente activo (se expande por defecto). */
export function phaseHasActive(phase: PhaseNav): boolean {
  return phase.agents.some((a) => a.enabled);
}

/** Estado de expansión por defecto: grupos con agente activo, abiertos. */
export function defaultOpenGroups(): Record<string, boolean> {
  return Object.fromEntries(ISDF_NAV.map((p) => [p.key, phaseHasActive(p)]));
}
