// Navegación por fases del ISDF. Solo el Agente EF (ESPECIFICAR) está activo;
// los demás agentes se muestran visibles pero deshabilitados ("próximamente").

export interface AgentNav {
  key: string;
  name: string;
  href?: string;
  enabled: boolean;
}

export interface PhaseNav {
  phase: string;
  agents: AgentNav[];
}

export const ISDF_NAV: PhaseNav[] = [
  {
    phase: "Especificar",
    agents: [{ key: "ef", name: "Agente EF", href: "/agents/ef", enabled: true }],
  },
  {
    phase: "Diseñar",
    agents: [
      { key: "arquitectura", name: "Arquitectura", enabled: false },
      { key: "bd", name: "Base de Datos", enabled: false },
    ],
  },
  {
    phase: "Construir",
    agents: [
      { key: "api", name: "API", enabled: false },
      { key: "backend", name: "Backend", enabled: false },
      { key: "frontend", name: "Frontend", enabled: false },
    ],
  },
  {
    phase: "Verificar",
    agents: [{ key: "qa", name: "QA", enabled: false }],
  },
  {
    phase: "Gestionar",
    agents: [
      { key: "scrum", name: "Agente Scrum", href: "/agents/scrum", enabled: true },
      { key: "devops", name: "DevOps", enabled: false },
    ],
  },
];
