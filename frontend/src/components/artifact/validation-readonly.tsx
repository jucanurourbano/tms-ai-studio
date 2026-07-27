"use client";

import { Eye } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { QuestionStatus } from "@/lib/types/ef";

const STATUS_STYLE: Record<QuestionStatus, string> = {
  pendiente: "border-slate-300 bg-slate-50 text-slate-600",
  confirmado: "border-emerald-300 bg-emerald-50 text-emerald-700",
  corregido: "border-amber-300 bg-amber-50 text-amber-700",
};

/**
 * Estado de una validación en **modo lectura**: mismo sitio y misma jerarquía
 * que los controles de escritura, pero sin caja de texto ni botones.
 *
 * Compartido por los tres agentes (EF, Scrum, Arquitectura), cuyos controles de
 * validación son equivalentes y solo difieren en la API que llaman.
 */
export function ValidationReadOnly({
  status,
  respuesta,
  className,
}: {
  status: QuestionStatus;
  respuesta?: string | null;
  className?: string;
}) {
  return (
    <div className={cn("mt-2 rounded-md border bg-muted/30 p-2", className)}>
      <div className="flex items-center gap-2">
        <span className="text-[11px] text-meta-foreground">Estado:</span>
        <Badge variant="outline" className={STATUS_STYLE[status]}>
          {status}
        </Badge>
        <span
          className="ml-auto inline-flex items-center gap-1 text-[11px] text-meta-foreground"
          title="Tu rol permite consultar este módulo, no responder"
        >
          <Eye className="h-3 w-3" />
          solo lectura
        </span>
      </div>
      {respuesta ? (
        <p className="mt-1.5 whitespace-pre-wrap text-xs text-muted-foreground">
          {respuesta}
        </p>
      ) : null}
    </div>
  );
}
