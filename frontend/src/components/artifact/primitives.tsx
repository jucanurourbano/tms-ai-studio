"use client";

// Primitivas visuales compartidas por las vistas de artefacto (EF y Scrum).
// Objetivo: presencia de producto (chips, cards con cabecera, listas hairline,
// mini-stats, pills de estado) en vez de "texto tipo Wikipedia".

import { Check, Minus } from "lucide-react";
import { toast } from "sonner";

import { cn } from "@/lib/utils";

/** Desplaza y resalta el elemento con id `ref-<refId>` (trazabilidad). */
export function jumpToRef(refId?: string | null) {
  if (!refId) return;
  const el = document.getElementById(`ref-${refId}`);
  if (!el) {
    toast.info(`Referencia ${refId} no visible en esta vista.`);
    return;
  }
  el.scrollIntoView({ behavior: "smooth", block: "center" });
  el.classList.add("ref-highlight");
  window.setTimeout(() => el.classList.remove("ref-highlight"), 1600);
}

/**
 * Chip de referencia CLICABLE (REQ-F-001, US-002…): monoespaciado, fondo suave,
 * borde sutil y hover violeta. Reemplaza los hipervínculos azules subrayados.
 */
export function RefChip({
  refId,
  className,
}: {
  refId?: string | null;
  className?: string;
}) {
  if (!refId) return null;
  return (
    <button
      type="button"
      onClick={() => jumpToRef(refId)}
      className={cn(
        "inline-flex items-center rounded-md border border-border/70 bg-muted/60 px-1.5 py-0.5 font-mono text-[11px] leading-none text-foreground/75 transition-colors hover:border-primary/40 hover:bg-primary/10 hover:text-primary",
        className,
      )}
    >
      {refId}
    </button>
  );
}

/** Etiqueta monoespaciada NO clicable: la identidad propia de una fila/ítem. */
export function IdTag({
  id,
  className,
}: {
  id: string;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md border border-border/60 bg-muted/50 px-1.5 py-0.5 font-mono text-[11px] leading-none text-muted-foreground",
        className,
      )}
    >
      {id}
    </span>
  );
}

/** Conteo como pill; ámbar cuando es 0 (estado vacío EXPLÍCITO, nunca oculto). */
export function CountChip({ n }: { n?: number }) {
  if (n === undefined) return null;
  const empty = n === 0;
  return (
    <span
      className={cn(
        "inline-flex min-w-5 items-center justify-center rounded-full px-1.5 py-0.5 text-[11px] font-semibold tabular-nums",
        empty
          ? "bg-amber-100 text-amber-700"
          : "bg-primary/10 text-primary",
      )}
    >
      {empty ? "0 ⚠" : n}
    </span>
  );
}

/**
 * Sección como card con cabecera propia (índice + título + conteo + acciones),
 * en vez de un título suelto sobre blanco infinito.
 */
export function SectionCard({
  id,
  index,
  title,
  count,
  actions,
  className,
  children,
}: {
  id?: string;
  index?: string;
  title: React.ReactNode;
  count?: number;
  actions?: React.ReactNode;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <section
      id={id}
      className={cn(
        "scroll-mt-28 overflow-hidden rounded-xl bg-card ring-1 ring-foreground/10 print-avoid-break",
        className,
      )}
    >
      <header className="flex items-center gap-2 border-b bg-muted/30 px-4 py-2.5">
        {index && (
          <span className="font-heading text-xs font-semibold tabular-nums text-muted-foreground">
            {index}
          </span>
        )}
        <h2 className="font-heading text-sm font-semibold tracking-tight">
          {title}
        </h2>
        {count !== undefined && <CountChip n={count} />}
        {actions && (
          <div className="ml-auto flex items-center gap-1.5">{actions}</div>
        )}
      </header>
      <div className="p-4">{children}</div>
    </section>
  );
}

/** Sub-encabezado dentro de una card (para agrupar bloques). */
export function GroupLabel({
  children,
  count,
}: {
  children: React.ReactNode;
  count?: number;
}) {
  return (
    <div className="mb-1.5 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
      {children}
      {count !== undefined && <CountChip n={count} />}
    </div>
  );
}

/** Contenedor de lista con separadores hairline. */
export function DataList({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "divide-y divide-border/60 overflow-hidden rounded-lg border",
        className,
      )}
    >
      {children}
    </div>
  );
}

/**
 * Fila de lista: número opcional a la izquierda, contenido flexible y una
 * columna derecha fija (chip de ref / badges). Hover suave.
 */
export function DataRow({
  id,
  index,
  right,
  className,
  children,
}: {
  id?: string;
  index?: number;
  right?: React.ReactNode;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div
      id={id ? `ref-${id}` : undefined}
      className={cn(
        "flex items-start gap-3 px-3 py-2 transition-colors hover:bg-primary/[0.04]",
        className,
      )}
    >
      {index !== undefined && (
        <span className="w-5 shrink-0 pt-0.5 text-right font-mono text-[11px] tabular-nums text-muted-foreground/70">
          {index}
        </span>
      )}
      <div className="min-w-0 flex-1 text-sm">{children}</div>
      {right && (
        <div className="flex shrink-0 items-center gap-1.5 pt-0.5">{right}</div>
      )}
    </div>
  );
}

/** Estado vacío elegante (sustituye al "0 ⚠" suelto). */
export function EmptyHint({
  children = "Sin elementos.",
  warn = true,
}: {
  children?: React.ReactNode;
  warn?: boolean;
}) {
  return (
    <div
      className={cn(
        "rounded-lg border border-dashed px-3 py-2.5 text-xs",
        warn
          ? "border-amber-300 bg-amber-50/60 text-amber-700"
          : "border-border text-muted-foreground",
      )}
    >
      {warn && <span className="mr-1">⚠</span>}
      {children}
    </div>
  );
}

/** Mini-estadística: icono + valor + etiqueta (para la cabecera del job). */
export function Stat({
  icon,
  value,
  label,
}: {
  icon: React.ReactNode;
  value: React.ReactNode;
  label: string;
}) {
  return (
    <div className="flex items-center gap-2.5">
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary [&_svg]:h-4 [&_svg]:w-4">
        {icon}
      </div>
      <div className="leading-tight">
        <div className="font-heading text-sm font-semibold tabular-nums">
          {value}
        </div>
        <div className="text-[11px] text-muted-foreground">{label}</div>
      </div>
    </div>
  );
}

export function StatRow({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-3">{children}</div>
  );
}

/** Pill de estado con icono (checks del semáforo compuesto). */
export function StatusPill({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium",
        ok
          ? "border-emerald-300 bg-emerald-50 text-emerald-700"
          : "border-slate-300 bg-slate-50 text-slate-500",
      )}
    >
      <span
        className={cn(
          "flex h-3.5 w-3.5 items-center justify-center rounded-full text-white",
          ok ? "bg-emerald-500" : "bg-slate-300",
        )}
      >
        {ok ? (
          <Check className="h-2.5 w-2.5" strokeWidth={3} />
        ) : (
          <Minus className="h-2.5 w-2.5" strokeWidth={3} />
        )}
      </span>
      {label}
    </span>
  );
}

/**
 * Portada de la vista imprimible (Exportar PDF). Solo visible al imprimir; salta
 * de página tras la portada.
 */
export function PrintCover({
  kind,
  title,
  subtitle,
  stats,
}: {
  kind: string;
  title: string;
  subtitle?: string;
  stats?: { label: string; value: string }[];
}) {
  return (
    <div className="hidden break-after-page print:block">
      <div className="flex min-h-[78vh] flex-col justify-between py-6 text-neutral-900">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.2em] text-violet-700">
            TMS AI Studio · ISDF · Urbano TI
          </div>
          <div className="mt-28">
            <div className="text-sm font-semibold text-neutral-500">{kind}</div>
            <h1 className="mt-2 text-4xl font-bold tracking-tight">{title}</h1>
            {subtitle && (
              <p className="mt-3 max-w-xl text-sm text-neutral-600">{subtitle}</p>
            )}
          </div>
        </div>
        {stats && stats.length > 0 && (
          <div className="grid grid-cols-2 gap-4 border-t border-neutral-200 pt-6 sm:grid-cols-4">
            {stats.map((s) => (
              <div key={s.label}>
                <div className="text-xl font-semibold tabular-nums">
                  {s.value}
                </div>
                <div className="text-xs text-neutral-500">{s.label}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
