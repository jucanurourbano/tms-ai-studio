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
      },
    ],
  },
  {
    key: "disenar",
    phase: "Diseñar",
    agents: [
      { key: "arquitectura", name: "Arquitectura", enabled: false, icon: "layers" },
      { key: "bd", name: "Base de Datos", enabled: false, icon: "database" },
    ],
  },
  {
    key: "construir",
    phase: "Construir",
    agents: [
      { key: "api", name: "API", enabled: false, icon: "plug" },
      { key: "backend", name: "Backend", enabled: false, icon: "server" },
      { key: "frontend", name: "Frontend", enabled: false, icon: "monitor" },
    ],
  },
  {
    key: "verificar",
    phase: "Verificar",
    agents: [{ key: "qa", name: "QA", enabled: false, icon: "shield-check" }],
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
      },
      { key: "devops", name: "DevOps", enabled: false, icon: "rocket" },
    ],
  },
];

/** Un grupo tiene al menos un agente activo (se expande por defecto). */
export function phaseHasActive(phase: PhaseNav): boolean {
  return phase.agents.some((a) => a.enabled);
}

/** Estado de expansión por defecto: grupos con agente activo, abiertos. */
export function defaultOpenGroups(): Record<string, boolean> {
  return Object.fromEntries(ISDF_NAV.map((p) => [p.key, phaseHasActive(p)]));
}
