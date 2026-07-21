// Renderiza la clave de icono del ISDF con el componente lucide correspondiente.
// Se usa un mapa de renderizadores con JSX estático (no se selecciona un
// componente a una variable en render) para cumplir `react-hooks/static-components`.
// Centralizado para reutilizar el mismo icono en la sidebar y en las cabeceras.

import {
  Database,
  FileSearch,
  Kanban,
  Layers,
  Monitor,
  Plug,
  Rocket,
  Server,
  ShieldCheck,
} from "lucide-react";

import type { AgentIcon } from "@/lib/isdf";

interface IconProps {
  className?: string;
}

const RENDERERS: Record<AgentIcon, (props: IconProps) => React.ReactNode> = {
  "file-search": (p) => <FileSearch {...p} />,
  kanban: (p) => <Kanban {...p} />,
  layers: (p) => <Layers {...p} />,
  database: (p) => <Database {...p} />,
  plug: (p) => <Plug {...p} />,
  server: (p) => <Server {...p} />,
  monitor: (p) => <Monitor {...p} />,
  "shield-check": (p) => <ShieldCheck {...p} />,
  rocket: (p) => <Rocket {...p} />,
};

export function AgentIconView({
  icon,
  className,
}: {
  icon: AgentIcon;
  className?: string;
}) {
  return RENDERERS[icon]({ className });
}
