"use client";

import { ChevronDown } from "lucide-react";
import { useState } from "react";

import { CountChip } from "@/components/artifact/primitives";
import { cn } from "@/lib/utils";

/**
 * Sección de artefacto con REVELACIÓN PROGRESIVA.
 *
 * Colapsada muestra solo cabecera (índice + título + conteo + meta) y un
 * `preview` de 1–2 líneas. Al abrirse expande su contenido completo en el mismo
 * flujo (acordeón). El contenido pesado se monta perezosamente (solo tras la
 * primera apertura) y se conserva montado para que reabrir sea instantáneo.
 *
 * En impresión (`forceRender`) todo se monta y expande para que el PDF incluya
 * el artefacto íntegro.
 */
export function ArtifactSection({
  id,
  index,
  title,
  count,
  meta,
  preview,
  open,
  onToggle,
  actions,
  forceRender = false,
  className,
  children,
}: {
  id?: string;
  index?: string;
  title: React.ReactNode;
  count?: number;
  meta?: React.ReactNode;
  /** Resumen breve visible cuando la sección está colapsada. */
  preview?: React.ReactNode;
  open: boolean;
  onToggle: () => void;
  actions?: React.ReactNode;
  /** Fuerza el montaje/expansión (impresión). */
  forceRender?: boolean;
  className?: string;
  children: React.ReactNode;
}) {
  // Latch de montaje perezoso: el contenido se monta al abrir por primera vez
  // (o al imprimir) y se conserva montado para que reabrir sea instantáneo y el
  // colapso pueda animarse. Patrón sancionado de "ajustar estado en render".
  const [everOpened, setEverOpened] = useState(open || forceRender);
  if ((open || forceRender) && !everOpened) {
    setEverOpened(true);
  }

  const mounted = everOpened;
  const expanded = open || forceRender;
  const panelId = id ? `${id}-panel` : undefined;

  return (
    <section
      id={id}
      data-open={open ? "" : undefined}
      className={cn(
        "scroll-mt-28 overflow-hidden rounded-xl bg-card ring-1 ring-foreground/10 transition-shadow duration-200 print:overflow-visible print:rounded-none print:ring-0",
        open && "shadow-sm ring-primary/25",
        className,
      )}
    >
      <div className="flex items-center gap-2 border-b bg-muted/30 px-4 py-2.5 print:border-b-2 print:border-violet-800/70 print:bg-transparent print:px-0">
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={open}
          aria-controls={panelId}
          className="group flex min-w-0 flex-1 items-center gap-2 text-left"
        >
          {index && (
            <span className="font-heading text-xs font-semibold tabular-nums text-meta-foreground print:text-violet-800">
              {index}
            </span>
          )}
          <h2 className="truncate font-heading text-base font-semibold tracking-tight transition-colors group-hover:text-primary print:text-violet-800">
            {title}
          </h2>
          {count !== undefined && <CountChip n={count} />}
          {meta && (
            <span className="truncate text-[11px] text-meta-foreground print:hidden">
              {meta}
            </span>
          )}
        </button>
        {actions && (
          <div className="flex shrink-0 items-center gap-1.5 print:hidden">
            {actions}
          </div>
        )}
        <button
          type="button"
          onClick={onToggle}
          aria-label={open ? "Colapsar sección" : "Expandir sección"}
          className="shrink-0 rounded-md p-0.5 text-muted-foreground transition-colors hover:text-primary print:hidden"
        >
          <ChevronDown
            className={cn(
              "h-4 w-4 transition-transform duration-200 ease-out",
              open && "rotate-180",
            )}
          />
        </button>
      </div>

      {/* Preview: solo colapsado y en pantalla; toda la tarjeta es clicable. */}
      {!open && preview && (
        <button
          type="button"
          onClick={onToggle}
          className="block w-full cursor-pointer px-4 py-3 text-left text-sm text-muted-foreground transition-colors hover:bg-primary/[0.03] print:hidden"
        >
          {preview}
        </button>
      )}

      {/* Contenido completo (lazy + animado). */}
      <div
        id={panelId}
        className={cn(
          "grid transition-[grid-template-rows] duration-200 ease-out print:grid-rows-[1fr]",
          expanded ? "grid-rows-[1fr]" : "grid-rows-[0fr]",
        )}
      >
        <div className="overflow-hidden print:overflow-visible">
          {mounted && <div className="p-4 print:px-0 print:py-3">{children}</div>}
        </div>
      </div>
    </section>
  );
}
