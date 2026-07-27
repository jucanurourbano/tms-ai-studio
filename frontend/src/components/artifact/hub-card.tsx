"use client";

// Tarjetas-sección del hub: el índice del artefacto convertido en botones.
//
// Cada tarjeta responde tres preguntas de un vistazo — qué sección es (icono con
// el acento del módulo), cuánto hay dentro (conteos) y si me reclama algo (línea
// de insight, en rojo cuando hay pendientes). Se sienten pulsables: elevación y
// anillo de acento al hover, chevron de afordancia y `aria-haspopup="dialog"`
// porque lo que abren es el panel lateral, no otra página.

import { AlertCircle, ChevronRight } from "lucide-react";

import { accentOf } from "@/lib/module-accent";
import type { ModuleKey } from "@/lib/types/auth";
import { cn } from "@/lib/utils";

export function HubGrid({ children }: { children: React.ReactNode }) {
  return (
    <div className="stagger-children grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {children}
    </div>
  );
}

/**
 * Pista de uso bajo el grid: dice en una línea que las tarjetas abren un panel y
 * qué teclas funcionan dentro. El hub es un patrón nuevo; una frase evita que el
 * usuario descubra los atajos por accidente (o nunca).
 */
export function HubHint() {
  return (
    <p className="mt-4 text-[11px] text-meta-foreground">
      Cada tarjeta abre su sección en el panel lateral. Dentro: <Kbd>←</Kbd>{" "}
      <Kbd>→</Kbd> cambian de sección, <Kbd>Esc</Kbd> cierra y los chips de
      referencia saltan a la sección que los define.
    </p>
  );
}

function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="rounded border bg-muted px-1 font-mono text-[10px] text-foreground/70">
      {children}
    </kbd>
  );
}

export function HubCard({
  module,
  icon,
  title,
  metrics,
  insight,
  urgent = false,
  urgentLabel,
  onOpen,
}: {
  /** Módulo del ISDF: de él sale el acento de color del icono. */
  module: ModuleKey;
  icon: React.ReactNode;
  title: string;
  /** Conteos clave, p. ej. "27 · 22 funcionales". */
  metrics?: React.ReactNode;
  /** Una línea: lo que el usuario necesita saber sin abrir. */
  insight?: React.ReactNode;
  /** Hay algo que reclama acción (bloqueantes, must sin asignar…). */
  urgent?: boolean;
  /** Texto del badge de urgencia (p. ej. "11 sin responder"). */
  urgentLabel?: string;
  onOpen: () => void;
}) {
  const accent = accentOf(module);
  return (
    <button
      type="button"
      onClick={onOpen}
      aria-haspopup="dialog"
      className={cn(
        "group relative flex min-h-28 flex-col items-start gap-2 rounded-xl bg-card p-4 text-left ring-1 transition-all duration-200 ease-out",
        "hover:-translate-y-0.5 hover:shadow-lg hover:shadow-foreground/5 focus-visible:ring-2 focus-visible:ring-primary focus-visible:outline-none",
        urgent
          ? "ring-red-300 hover:ring-red-400"
          : "ring-foreground/10 hover:ring-primary/30",
      )}
    >
      {/* Barra de urgencia: el borde izquierdo grita antes que el texto. */}
      {urgent && (
        <span
          className="absolute inset-y-3 left-0 w-0.5 rounded-full bg-red-500"
          aria-hidden
        />
      )}

      <div className="flex w-full items-start gap-3">
        <span
          className={cn(
            "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg transition-transform duration-200 ease-out group-hover:scale-105 [&_svg]:h-4.5 [&_svg]:w-4.5",
            accent.soft,
          )}
        >
          {icon}
        </span>
        <span className="min-w-0 flex-1">
          <span
            className={cn(
              "block font-heading text-sm font-semibold tracking-tight transition-colors",
              accent.groupHoverText,
            )}
          >
            {title}
          </span>
          {metrics && (
            <span className="mt-0.5 block text-xs tabular-nums text-muted-foreground">
              {metrics}
            </span>
          )}
        </span>
        <ChevronRight className="h-4 w-4 shrink-0 text-meta-foreground transition-transform duration-200 ease-out group-hover:translate-x-0.5 group-hover:text-primary" />
      </div>

      {insight && (
        <span
          className={cn(
            "mt-auto inline-flex items-start gap-1.5 text-xs leading-snug",
            urgent ? "font-medium text-red-600" : "text-meta-foreground",
          )}
        >
          {urgent && <AlertCircle className="mt-px h-3.5 w-3.5 shrink-0" />}
          {insight}
        </span>
      )}

      {urgent && urgentLabel && (
        <span className="absolute top-3 right-9 inline-flex items-center rounded-full bg-red-600 px-1.5 py-0.5 text-[10px] font-semibold tabular-nums text-white">
          {urgentLabel}
        </span>
      )}
    </button>
  );
}
