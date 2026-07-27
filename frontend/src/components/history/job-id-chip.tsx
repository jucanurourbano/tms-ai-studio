"use client";

import { Check, Copy } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { cn } from "@/lib/utils";

/** Cuántos caracteres finales del ULID se muestran. */
const VISIBLES = 8;

/**
 * Id de job en **versión corta** (últimos 8 caracteres) con el completo en el
 * tooltip y **copiar al clic**.
 *
 * Un ULID entero (26 caracteres) ocupaba en la tabla casi tanto como el título y
 * no se lee: nadie identifica un job "de vista" por su id, solo lo necesita para
 * pegarlo en un comando o un mensaje. Mostrar la cola es suficiente para
 * distinguir dos filas, y el espacio liberado se lo queda el título.
 *
 * El clic **no propaga**: la fila entera es clicable y copiar no debe navegar.
 */
export function JobIdChip({
  id,
  className,
}: {
  id: string;
  className?: string;
}) {
  const [copiado, setCopiado] = useState(false);
  const corto = id.length > VISIBLES ? id.slice(-VISIBLES) : id;

  async function copiar(e: React.MouseEvent) {
    e.stopPropagation();
    e.preventDefault();
    try {
      await navigator.clipboard.writeText(id);
      setCopiado(true);
      toast.success("Id copiado", { description: id });
      window.setTimeout(() => setCopiado(false), 1500);
    } catch {
      toast.error("No se pudo copiar el id.");
    }
  }

  return (
    <button
      type="button"
      onClick={copiar}
      title={`${id}\n(clic para copiar)`}
      aria-label={`Copiar id completo ${id}`}
      className={cn(
        "group/id inline-flex items-center gap-1 rounded-md border border-border/60 bg-muted/50 px-1.5 py-0.5 font-mono text-[11px] leading-none text-meta-foreground transition-colors hover:border-primary/40 hover:bg-primary/10 hover:text-primary",
        className,
      )}
    >
      <span aria-hidden className="opacity-50">
        …
      </span>
      {corto}
      {copiado ? (
        <Check className="h-3 w-3 text-emerald-600" />
      ) : (
        <Copy className="h-3 w-3 opacity-0 transition-opacity group-hover/id:opacity-100" />
      )}
    </button>
  );
}
