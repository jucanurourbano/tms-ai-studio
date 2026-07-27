"use client";

import type { JobStatusCounts, JobStatusGroup } from "@/lib/types/ef";
import { cn } from "@/lib/utils";

/** Definición de cada pestaña: etiqueta y punto de color del estado. */
const TABS: {
  group: JobStatusGroup;
  label: string;
  dot: string;
  activo: string;
}[] = [
  {
    group: "completados",
    label: "Completados",
    dot: "bg-emerald-500",
    activo: "border-emerald-300 bg-emerald-50 text-emerald-800",
  },
  {
    group: "avisos",
    label: "Con avisos",
    dot: "bg-amber-500",
    activo: "border-amber-300 bg-amber-50 text-amber-800",
  },
  {
    group: "en_proceso",
    label: "En proceso",
    dot: "bg-sky-500",
    activo: "border-sky-300 bg-sky-50 text-sky-800",
  },
  {
    group: "fallidos",
    label: "Fallidos",
    dot: "bg-red-500",
    activo: "border-red-300 bg-red-50 text-red-800",
  },
  {
    group: "todos",
    label: "Todos",
    dot: "bg-slate-400",
    activo: "border-slate-300 bg-slate-100 text-slate-800",
  },
];

/**
 * Filtro del historial por grupo de estado, como **segmented control con
 * contadores**.
 *
 * Cada pestaña lleva su punto de color (el mismo lenguaje que las pills de estado
 * de la tabla) y el número de jobs de ese grupo, que viene del backend y cuenta
 * sobre TODOS los jobs del agente — no sobre la página cargada.
 *
 * Una pestaña con 0 jobs se muestra igualmente, atenuada y deshabilitada: decir
 * "Fallidos (0)" informa; ocultarla dejaría la duda de si el filtro existe.
 * `Todos` nunca se deshabilita, para que siempre haya una salida.
 *
 * En móvil la fila hace scroll horizontal: son cinco pestañas y apilarlas robaría
 * la pantalla que necesita la lista.
 */
export function JobStatusTabs({
  value,
  counts,
  onChange,
  disabled = false,
}: {
  value: JobStatusGroup;
  counts?: JobStatusCounts;
  onChange: (group: JobStatusGroup) => void;
  disabled?: boolean;
}) {
  return (
    <div
      role="tablist"
      aria-label="Filtrar por estado"
      // `-mx-1 px-1`: deja respirar el anillo de foco del primer/último tab al
      // hacer scroll.
      className="-mx-1 flex gap-1.5 overflow-x-auto px-1 pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
    >
      {TABS.map((tab) => {
        const n = counts?.[tab.group];
        const activo = value === tab.group;
        const vacio = n === 0 && tab.group !== "todos";
        return (
          <button
            key={tab.group}
            type="button"
            role="tab"
            aria-selected={activo}
            disabled={disabled || vacio}
            onClick={() => onChange(tab.group)}
            title={vacio ? `Sin jobs ${tab.label.toLowerCase()}` : undefined}
            className={cn(
              "inline-flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50",
              activo
                ? tab.activo
                : "border-border bg-card text-muted-foreground hover:bg-muted",
              vacio && !activo && "opacity-45",
              (disabled || vacio) && "cursor-not-allowed",
            )}
          >
            <span
              aria-hidden
              className={cn("h-1.5 w-1.5 shrink-0 rounded-full", tab.dot)}
            />
            {tab.label}
            {n !== undefined && (
              <span
                className={cn(
                  "font-mono tabular-nums",
                  activo ? "opacity-80" : "text-meta-foreground",
                )}
              >
                {n}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
