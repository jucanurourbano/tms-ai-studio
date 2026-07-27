"use client";

// Tarjetas-sección del hub: el índice del artefacto convertido en botones.
//
// Cada tarjeta responde tres preguntas de un vistazo — qué sección es (icono con
// el acento del módulo), cuánto hay dentro (conteos) y si me reclama algo (línea
// de insight, en rojo cuando hay pendientes). Se sienten pulsables: elevación y
// anillo del acento al hover, chevron de afordancia y `aria-haspopup="dialog"`
// porque lo que abren es el panel lateral, no otra página.

import { AlertCircle, ChevronRight, Keyboard } from "lucide-react";

import {
  patternClassOf,
  toneOf,
  type SectionPattern,
  type SectionTone,
} from "@/lib/card-accent";
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
    <div className="stagger-children mx-auto flex max-w-5xl flex-wrap justify-center gap-7">
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
  tone,
  pattern,
  icon,
  title,
  stat,
  metrics,
  insight,
  urgent = false,
  urgentLabel,
  prominent = false,
  onOpen,
}: {
  /** Tono propio de la sección; `urgent` lo sustituye por el rojo. */
  tone?: SectionTone;
  /** Textura de fondo, solo si dice algo de la naturaleza de la sección. */
  pattern?: SectionPattern;
  icon: React.ReactNode;
  title: string;
  /** La cifra protagonista y su etiqueta ("27" / "requisitos"). */
  stat?: { value: React.ReactNode; label: string };
  /** Alternativa a `stat` cuando la sección no se resume en un número. */
  metrics?: React.ReactNode;
  /** Una línea: lo que el usuario necesita saber sin abrir. */
  insight?: React.ReactNode;
  /** Hay algo que reclama acción (bloqueantes, must sin asignar…). */
  urgent?: boolean;
  /** Texto del badge de urgencia (p. ej. "11"). */
  urgentLabel?: string;
  /** Fila superior del hub: las secciones de decisión piden algo más de aire. */
  prominent?: boolean;
  onOpen: () => void;
}) {
  const t = toneOf(urgent ? "danger" : tone);
  const patternClass = patternClassOf(pattern);
  return (
    <button
      type="button"
      onClick={onOpen}
      aria-haspopup="dialog"
      className={cn(
        // Anchos explícitos porque el contenedor es flex: 1 / 2 / 3 columnas.
        "w-full sm:w-[calc(50%-0.875rem)] lg:w-[calc(33.333%-1.167rem)]",
        "group relative flex min-h-40 flex-col overflow-hidden rounded-2xl bg-card p-5 pt-6 text-left ring-1 transition-all duration-200 ease-out",
        // Elevación + glow del tono: el hover confirma que la tarjeta es un botón.
        "hover:-translate-y-0.5 hover:shadow-xl focus-visible:ring-2 focus-visible:ring-primary focus-visible:outline-none",
        t.hoverGlow,
        urgent ? "ring-red-300" : "ring-foreground/10",
        t.hoverRing,
        // La fila de decisión respira un poco más (solo donde hay tres columnas).
        prominent && "lg:min-h-48",
      )}
    >
      {/* (b) Barra de acento del canto superior: identifica la sección de lejos. */}
      <span
        className={cn("absolute inset-x-0 top-0 h-[3px]", t.bar)}
        aria-hidden
      />
      {/* Textura decorativa, confinada a la esquina y al 6% de opacidad. */}
      {patternClass && (
        <span className={cn("hub-pattern", patternClass, t.pattern)} aria-hidden />
      )}

      <div className="relative flex w-full items-center gap-3">
        {/* (a) Icono con degradado del acento y una esquina distinta: un guiño
            de forma dentro de la misma retícula, no una silueta. */}
        <span
          className={cn(
            "flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl rounded-bl-md ring-1 ring-inset ring-foreground/5 transition-transform duration-200 ease-out group-hover:scale-105 [&_svg]:h-5 [&_svg]:w-5",
            t.icon,
          )}
        >
          {icon}
        </span>
        <span className="min-w-0 flex-1 font-heading text-[15px] font-semibold tracking-tight">
          {title}
        </span>
        {urgent && urgentLabel && (
          <span className="inline-flex shrink-0 items-center rounded-full bg-red-600 px-1.5 py-0.5 text-[10px] font-semibold tabular-nums text-white">
            {urgentLabel}
          </span>
        )}
        <ChevronRight className="h-4 w-4 shrink-0 text-meta-foreground transition-transform duration-200 ease-out group-hover:translate-x-0.5 group-hover:text-foreground/70" />
      </div>

      {/* La cifra es el protagonista visual: se lee antes que el título. */}
      {stat ? (
        <span className="relative mt-3 block">
          <span
            className={cn(
              "block font-heading text-[22px] font-semibold leading-none tabular-nums",
              t.number,
            )}
          >
            {stat.value}
          </span>
          <span className="mt-1 block text-[11px] text-meta-foreground">
            {stat.label}
          </span>
        </span>
      ) : (
        metrics && (
          <span className="relative mt-3 block text-xs text-muted-foreground">
            {metrics}
          </span>
        )
      )}

      {insight && (
        // Hairline: separa "cuánto hay" (arriba) de "qué me reclama" (abajo).
        <span
          className={cn(
            "relative mt-auto flex items-start gap-1.5 border-t pt-3 text-xs leading-snug",
            urgent
              ? "border-red-200 font-medium text-red-600"
              : "border-border/60 text-meta-foreground",
          )}
        >
          {urgent && <AlertCircle className="mt-px h-3.5 w-3.5 shrink-0" />}
          {insight}
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
