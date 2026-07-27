"use client";

// MODO ENFOCADO para responder preguntas de afinamiento: una pregunta a la vez,
// con su contexto, barra de progreso y avance automático al responder.
//
// Antes vivía en su propio sheet; ahora es un BLOQUE que se monta dentro del
// panel lateral universal, en la sección "Preguntas". Es el mismo patrón (era el
// correcto) con la estética unificada: el usuario no distingue dos paneles
// distintos, solo dos formas de mirar la misma sección — lista o una a una.

import { CheckCircle2, ChevronLeft, ChevronRight } from "lucide-react";
import { useState } from "react";

import { AudienceBadge } from "@/components/ef/badges";
import { RefChip } from "@/components/artifact/primitives";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { QuestionStatus } from "@/lib/types/ef";
import { cn } from "@/lib/utils";

export interface SheetQuestion {
  id: string;
  question: string;
  reason?: string;
  blocking?: boolean;
  audience?: "negocio" | "tecnico";
  linked_to_ref?: string | null;
}

const STATUS_LABEL: Record<QuestionStatus, string> = {
  pendiente: "Pendiente",
  confirmado: "Confirmada",
  corregido: "Corregida",
};

export function FocusedQuestionFlow({
  questions,
  statusOf,
  renderControls,
}: {
  questions: SheetQuestion[];
  statusOf: (id: string) => QuestionStatus;
  /** Controles de validación del agente; llama a `onAnswered` al guardar. */
  renderControls: (q: SheetQuestion, onAnswered: () => void) => React.ReactNode;
}) {
  // Arranca en la primera pregunta pendiente (o la primera si todas resueltas).
  const [index, setIndex] = useState(() => {
    const i = questions.findIndex((q) => statusOf(q.id) === "pendiente");
    return i === -1 ? 0 : i;
  });

  if (questions.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No hay preguntas para responder.
      </p>
    );
  }

  const total = questions.length;
  const answered = questions.filter((q) => statusOf(q.id) !== "pendiente").length;
  const position = Math.min(index, total - 1);
  const current = questions[position];
  const status = statusOf(current.id);

  const goNext = () => setIndex((i) => Math.min(i + 1, total - 1));
  const goPrev = () => setIndex((i) => Math.max(i - 1, 0));

  const pct = Math.round((answered / total) * 100);
  const allDone = answered >= total;

  return (
    <div className="flex min-h-full flex-col">
      {/* Progreso del afinamiento */}
      <div className="mb-3">
        <div className="flex items-center gap-2 text-[11px] text-meta-foreground">
          <span className="tabular-nums">
            {answered} de {total} respondidas
          </span>
          {allDone && (
            <span className="inline-flex items-center gap-1 font-medium text-emerald-600">
              <CheckCircle2 className="h-3.5 w-3.5" /> completo
            </span>
          )}
          <span className="ml-auto tabular-nums">
            Pregunta {position + 1} de {total}
          </span>
        </div>
        <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-muted">
          <div
            className={cn(
              "h-full rounded-full transition-[width] duration-300 ease-out",
              allDone ? "bg-emerald-500" : "bg-primary",
            )}
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>

      <div className="rounded-xl border p-4">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <span className="inline-flex items-center rounded-md border border-border/60 bg-muted/50 px-1.5 py-0.5 font-mono text-[11px] leading-none text-meta-foreground">
            {current.id}
          </span>
          {current.audience && <AudienceBadge audience={current.audience} />}
          {current.blocking && <Badge className="bg-red-600">bloqueante</Badge>}
          <Badge
            variant="outline"
            className={cn(
              "ml-auto",
              status === "confirmado" &&
                "border-emerald-300 bg-emerald-50 text-emerald-700",
              status === "corregido" &&
                "border-amber-300 bg-amber-50 text-amber-700",
              status === "pendiente" && "border-slate-300 bg-slate-50 text-slate-600",
            )}
          >
            {STATUS_LABEL[status]}
          </Badge>
        </div>

        <p className="text-[15px] font-medium leading-relaxed">
          {current.question}
        </p>
        {current.reason && (
          <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">
            Motivo: {current.reason}
          </p>
        )}
        {current.linked_to_ref && (
          <p className="mt-1.5 inline-flex items-center gap-1 text-xs text-muted-foreground">
            ligada a <RefChip refId={current.linked_to_ref} />
          </p>
        )}

        <div className="mt-4">{renderControls(current, goNext)}</div>
      </div>

      <div className="mt-auto flex items-center gap-2 pt-3">
        <Button
          variant="outline"
          size="sm"
          className="gap-1"
          onClick={goPrev}
          disabled={position <= 0}
        >
          <ChevronLeft className="h-3.5 w-3.5" />
          Anterior
        </Button>
        <span className="mx-auto text-[11px] tabular-nums text-meta-foreground">
          {position + 1} / {total}
        </span>
        <Button
          variant="outline"
          size="sm"
          className="gap-1"
          onClick={goNext}
          disabled={position >= total - 1}
        >
          Siguiente
          <ChevronRight className="h-3.5 w-3.5" />
        </Button>
      </div>
    </div>
  );
}
