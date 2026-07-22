// Navegación por fases del ISDF. Los agentes EF (ESPECIFICAR) y Scrum (GESTIONAR)
// están activos; los demás se muestran visibles pero deshabilitados ("próximamente").
//
// Los iconos se referencian por clave (string) y se resuelven a componentes lucide
// en la sidebar, para mantener este módulo libre de dependencias de UI.

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
        name: "Arquitectura",
        enabled: false,
        icon: "layers",
        description:
          "Define la arquitectura técnica de la solución a partir de la EF y el plan ágil.",
      },
      {
        key: "bd",
        name: "Base de Datos",
        enabled: false,
        icon: "database",
        description:
          "Diseña el modelo de datos y el esquema de base de datos.",
      },
    ],
  },
  {
    key: "construir",
    phase: "Construir",
    agents: [
      {
        key: "api",
        name: "API",
        enabled: false,
        icon: "plug",
        description: "Especifica los contratos de API: endpoints y payloads.",
      },
      {
        key: "backend",
        name: "Backend",
        enabled: false,
        icon: "server",
        description: "Genera la capa de servicios y la lógica de negocio.",
      },
      {
        key: "frontend",
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
        name: "Agente Scrum",
        href: "/agents/scrum",
        enabled: true,
        icon: "kanban",
        description:
          "Genera épicas, historias, criterios, estimaciones y plan de sprints desde una EF lista.",
      },
      {
        key: "devops",
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

/** Un grupo tiene al menos un agente activo (se expande por defecto). */
export function phaseHasActive(phase: PhaseNav): boolean {
  return phase.agents.some((a) => a.enabled);
}

/** Estado de expansión por defecto: grupos con agente activo, abiertos. */
export function defaultOpenGroups(): Record<string, boolean> {
  return Object.fromEntries(ISDF_NAV.map((p) => [p.key, phaseHasActive(p)]));
}
