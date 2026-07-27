"use client";

// Tarjetas-sección del hub: el índice del artefacto convertido en botones.
//
// Cada tarjeta responde tres preguntas de un vistazo — qué sección es (icono con
// el acento del módulo), cuánto hay dentro (conteos) y si me reclama algo (línea
// de insight, en rojo cuando hay pendientes). Se sienten pulsables: elevación y
// anillo del acento al hover, chevron de afordancia y `aria-haspopup="dialog"`
// porque lo que abren es el panel lateral, no otra página.

import { AlertCircle, ChevronRight, Keyboard } from "lucide-react";

import { accentOf } from "@/lib/module-accent";
import type { ModuleKey } from "@/lib/types/auth";
import { cn } from "@/lib/utils";

/**
 * Rejilla del hub: **flex con envoltura y centrado**, no `grid`.
 *
 * Con `grid-cols-3` y cinco secciones la última fila queda pegada a la izquierda
 * y con un hueco a la derecha que se lee como "falta algo". Envolviendo y
 * centrando, 5 tarjetas caen como 3 + 2 centradas, 6 como 3 + 3 y 9 como 3 × 3 —
 * equilibrado sea cual sea el agente, sin casos especiales por número.
 *
 * El `max-w-5xl` evita que cinco tarjetas naden en un monitor ancho.
 */
export function HubGrid({ children }: { children: React.ReactNode }) {
  return (
    <div className="stagger-children mx-auto flex max-w-5xl flex-wrap justify-center gap-4">
      {children}
    </div>
  );
}

/**
 * Pista de atajos bajo el grid. Deliberadamente discreta: es una ayuda de
 * descubrimiento, no contenido — se lee una vez y luego debe desaparecer del
 * campo visual.
 */
export function HubHint() {
  return (
    <p className="mx-auto mt-5 flex max-w-5xl items-center justify-center gap-1.5 text-[10px] text-meta-foreground/80">
      <Keyboard className="h-3 w-3 shrink-0" aria-hidden />
      <span>
        <Kbd>←</Kbd> <Kbd>→</Kbd> cambian de sección · <Kbd>Esc</Kbd> cierra · los
        chips de referencia saltan a la sección que los define
      </span>
    </p>
  );
}

function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="rounded border bg-muted/70 px-1 font-mono text-[9px] text-foreground/60">
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
        // Anchos explícitos porque el contenedor es flex: 1 / 2 / 3 columnas.
        "w-full sm:w-[calc(50%-0.5rem)] lg:w-[calc(33.333%-0.667rem)]",
        "group relative flex min-h-32 flex-col rounded-2xl bg-card p-4 text-left ring-1 transition-all duration-200 ease-out",
        "hover:-translate-y-0.5 hover:shadow-lg hover:shadow-foreground/5 focus-visible:ring-2 focus-visible:ring-primary focus-visible:outline-none",
        urgent
          ? "ring-red-300 hover:ring-red-400"
          : cn("ring-foreground/10", accent.hoverRing),
      )}
    >
      {/* Barra de urgencia: el borde izquierdo grita antes que el texto. */}
      {urgent && (
        <span
          className="absolute inset-y-4 left-0 w-0.5 rounded-full bg-red-500"
          aria-hidden
        />
      )}

      <div className="flex w-full items-start gap-3">
        <span
          className={cn(
            "flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ring-1 ring-inset ring-foreground/5 transition-transform duration-200 ease-out group-hover:scale-105 [&_svg]:h-5 [&_svg]:w-5",
            urgent
              ? "bg-gradient-to-br from-red-100 to-red-50 text-red-600"
              : accent.iconGradient,
          )}
        >
          {icon}
        </span>
        <span className="min-w-0 flex-1">
          <span
            className={cn(
              "block font-heading text-[15px] font-semibold tracking-tight transition-colors",
              accent.groupHoverText,
            )}
          >
            {title}
          </span>
          {metrics && (
            <span className="mt-1 block text-xs tabular-nums text-muted-foreground">
              {metrics}
            </span>
          )}
        </span>
        <ChevronRight className="h-4 w-4 shrink-0 text-meta-foreground transition-transform duration-200 ease-out group-hover:translate-x-0.5 group-hover:text-foreground/70" />
      </div>

      {insight && (
        // Hairline: separa "cuánto hay" (arriba) de "qué me reclama" (abajo).
        <span
          className={cn(
            "mt-auto flex items-start gap-1.5 border-t pt-2.5 text-xs leading-snug",
            urgent
              ? "border-red-200 font-medium text-red-600"
              : "border-border/60 text-meta-foreground",
          )}
        >
          {urgent && <AlertCircle className="mt-px h-3.5 w-3.5 shrink-0" />}
          {insight}
        </span>
      )}

      {urgent && urgentLabel && (
        <span className="absolute top-3.5 right-9 inline-flex items-center rounded-full bg-red-600 px-1.5 py-0.5 text-[10px] font-semibold tabular-nums text-white">
          {urgentLabel}
        </span>
      )}
    </button>
  );
}

/**
 * Acciones de la cabecera del job agrupadas por intención (preguntas | exportes |
 * regenerar), con un hairline entre grupos. Sin la separación, ocho botones
 * seguidos se leen como una lista indiferenciada.
 *
 * El hairline solo aparece en `md+`: en móvil los grupos caen en líneas distintas
 * y un borde izquierdo al principio de la línea se lee como una marca suelta.
 */
export function HeaderActions({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2 md:[&>*+*]:border-l md:[&>*+*]:border-border/70 md:[&>*+*]:pl-3">
      {children}
    </div>
  );
}

export function ActionGroup({ children }: { children: React.ReactNode }) {
  return <div className="flex flex-wrap items-center gap-1.5">{children}</div>;
}
