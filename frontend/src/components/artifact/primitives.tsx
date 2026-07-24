"use client";

// Primitivas visuales compartidas por las vistas de artefacto (EF y Scrum).
// Objetivo: presencia de producto (chips, cards con cabecera, listas hairline,
// mini-stats, pills de estado) en vez de "texto tipo Wikipedia".

import { Check, Minus } from "lucide-react";
import Image from "next/image";
import { useEffect, useState } from "react";
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
        "print-color inline-flex items-center rounded-md border border-border/70 bg-muted/60 px-1.5 py-0.5 font-mono text-[11px] leading-none text-foreground/75 transition-colors hover:border-primary/40 hover:bg-primary/10 hover:text-primary",
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
        "print-color inline-flex items-center rounded-md border border-border/60 bg-muted/50 px-1.5 py-0.5 font-mono text-[11px] leading-none text-meta-foreground",
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
        "print-color inline-flex min-w-5 items-center justify-center rounded-full px-1.5 py-0.5 text-[11px] font-semibold tabular-nums print:bg-transparent print:text-neutral-500",
        empty ? "bg-amber-100 text-amber-700" : "bg-primary/10 text-primary",
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
        "scroll-mt-28 overflow-hidden rounded-xl bg-card ring-1 ring-foreground/10 print:overflow-visible print:rounded-none print:ring-0",
        className,
      )}
    >
      <header className="print-heading flex items-center gap-2 border-b bg-muted/30 px-4 py-2.5 print:border-b-2 print:border-violet-800/70 print:bg-transparent print:px-0">
        {index && (
          <span className="font-heading text-xs font-semibold tabular-nums text-meta-foreground print:text-violet-800">
            {index}
          </span>
        )}
        <h2 className="font-heading text-base font-semibold tracking-tight print:text-base print:text-violet-800">
          {title}
        </h2>
        {count !== undefined && <CountChip n={count} />}
        {actions && (
          <div className="ml-auto flex items-center gap-1.5 print:hidden">
            {actions}
          </div>
        )}
      </header>
      <div className="p-4 print:px-0 print:py-3">{children}</div>
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
    <div className="mb-1.5 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wide text-meta-foreground">
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
        "print-atom flex items-start gap-3 px-3 py-2 transition-colors hover:bg-primary/[0.04]",
        className,
      )}
    >
      {index !== undefined && (
        <span className="w-5 shrink-0 pt-0.5 text-right font-mono text-[11px] tabular-nums text-meta-foreground">
          {index}
        </span>
      )}
      <div className="min-w-0 flex-1 text-sm leading-relaxed">{children}</div>
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
        <div className="text-[11px] text-meta-foreground">{label}</div>
      </div>
    </div>
  );
}

export function StatRow({ children }: { children: React.ReactNode }) {
  return (
    <div className="print-atom flex flex-wrap items-center gap-x-6 gap-y-3">
      {children}
    </div>
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
 * Portada de la vista imprimible (Exportar PDF): logo, tipo de documento,
 * título, versión + fecha y una ficha de métricas clave. Solo visible al
 * imprimir; salta de página tras la portada. La fecha se calcula en el cliente
 * (tras montar) para no provocar desajustes de hidratación.
 */
export function PrintCover({
  kind,
  title,
  subtitle,
  version,
  stats,
}: {
  kind: string;
  title: string;
  subtitle?: string;
  version?: string;
  stats?: { label: string; value: string }[];
}) {
  const [date, setDate] = useState("");
  useEffect(() => {
    // Fuera del cuerpo síncrono del efecto (evita el warning de cascada) y sin
    // desajuste de hidratación: la fecha se calcula tras montar en el cliente.
    let cancelled = false;
    Promise.resolve().then(() => {
      if (cancelled) return;
      setDate(
        new Date().toLocaleDateString("es-PE", {
          year: "numeric",
          month: "long",
          day: "numeric",
        }),
      );
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="print-color hidden break-after-page print:block">
      <div className="flex min-h-[86vh] flex-col text-neutral-900">
        {/* Cabecera de marca */}
        <div className="flex items-center gap-3 border-b border-neutral-200 pb-4">
          <Image
            src="/logo-urbano.png"
            alt="Urbano"
            width={40}
            height={40}
            className="rounded-lg"
          />
          <div className="text-[11px] font-semibold uppercase tracking-[0.2em] text-violet-700">
            TMS AI Studio · ISDF · Urbano TI
          </div>
        </div>

        {/* Título del documento */}
        <div className="mt-28">
          <div className="text-sm font-semibold text-neutral-500">{kind}</div>
          <h1 className="mt-2 text-4xl font-bold leading-tight tracking-tight">
            {title}
          </h1>
          {subtitle && (
            <p className="mt-3 max-w-xl text-sm leading-relaxed text-neutral-600">
              {subtitle}
            </p>
          )}
          <div className="mt-5 flex flex-wrap gap-x-6 gap-y-1 text-xs text-neutral-500">
            {version && (
              <span>
                <span className="font-semibold text-neutral-700">Versión:</span>{" "}
                {version}
              </span>
            )}
            {date && (
              <span>
                <span className="font-semibold text-neutral-700">Fecha:</span>{" "}
                {date}
              </span>
            )}
          </div>
        </div>

        {/* Ficha de métricas clave */}
        {stats && stats.length > 0 && (
          <div className="mt-auto overflow-hidden rounded-xl border border-neutral-300">
            <div className="border-b border-neutral-200 bg-neutral-50 px-4 py-2 text-[11px] font-semibold uppercase tracking-wide text-neutral-500">
              Métricas clave
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4">
              {stats.map((s, i) => (
                <div
                  key={s.label}
                  className={cn(
                    "px-4 py-3",
                    i > 0 && "border-l border-neutral-200",
                  )}
                >
                  <div className="text-2xl font-bold tabular-nums text-neutral-900">
                    {s.value}
                  </div>
                  <div className="text-xs text-neutral-500">{s.label}</div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/** Índice del documento imprimible (lista numerada de secciones). */
export function PrintToc({ items }: { items: string[] }) {
  return (
    <div className="hidden break-after-page print:block">
      <h2 className="border-b-2 border-violet-800/70 pb-2 font-heading text-lg font-bold text-violet-800">
        Contenido
      </h2>
      <ol className="mt-5 space-y-3 text-sm text-neutral-800">
        {items.map((label, i) => (
          <li key={label} className="flex gap-3">
            <span className="w-5 shrink-0 text-right font-mono text-neutral-400">
              {i + 1}
            </span>
            <span>{label}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}

/** Pie de página propio, repetido en cada hoja impresa (marca + título). */
export function PrintFooter({ title }: { title: string }) {
  return (
    <div className="print-running-footer print-color" aria-hidden>
      <span>TMS AI Studio · Urbano TI</span>
      <span>{title}</span>
    </div>
  );
}

/** Estado de validación en la impresión (las preguntas conservan su estado). */
export function PrintValidationState({
  status,
  respuesta,
}: {
  status: string;
  respuesta?: string | null;
}) {
  const label =
    status === "confirmado"
      ? "Confirmada"
      : status === "corregido"
        ? "Corregida"
        : "Pendiente";
  return (
    <div className="mt-2 hidden border-t border-neutral-200 pt-1.5 text-xs print:block">
      <span className="font-semibold">Estado:</span> {label}
      {respuesta ? (
        <div className="mt-0.5 text-neutral-700">
          <span className="font-semibold">Respuesta:</span> {respuesta}
        </div>
      ) : null}
    </div>
  );
}
