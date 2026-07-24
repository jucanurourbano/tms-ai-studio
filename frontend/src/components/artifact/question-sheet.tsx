"use client";

import { CheckCircle2, ChevronLeft, ChevronRight } from "lucide-react";
import { useState } from "react";

import { AudienceBadge } from "@/components/ef/badges";
import { RefChip } from "@/components/artifact/primitives";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
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

/**
 * Modo enfocado para responder preguntas de afinamiento: un panel lateral que
 * presenta UNA pregunta a la vez con su contexto y avanza automáticamente a la
 * siguiente al responder. Barra de progreso arriba. Reutiliza los controles de
 * validación de cada agente vía `renderControls`.
 */
export function QuestionSheet({
  open,
  onOpenChange,
  questions,
  statusOf,
  title = "Responder preguntas",
  renderControls,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  questions: SheetQuestion[];
  statusOf: (id: string) => QuestionStatus;
  title?: string;
  /** Controles de validación del agente; llama a `onAnswered` al guardar. */
  renderControls: (q: SheetQuestion, onAnswered: () => void) => React.ReactNode;
}) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent aria-describedby={undefined}>
        {open && questions.length > 0 ? (
          <FocusedFlow
            questions={questions}
            statusOf={statusOf}
            title={title}
            renderControls={renderControls}
          />
        ) : (
          <>
            <SheetHeader>
              <SheetTitle>{title}</SheetTitle>
            </SheetHeader>
            <SheetBody>
              <p className="text-sm text-muted-foreground">
                No hay preguntas para responder.
              </p>
            </SheetBody>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}

function FocusedFlow({
  questions,
  statusOf,
  title,
  renderControls,
}: {
  questions: SheetQuestion[];
  statusOf: (id: string) => QuestionStatus;
  title: string;
  renderControls: (q: SheetQuestion, onAnswered: () => void) => React.ReactNode;
}) {
  // Arranca en la primera pregunta pendiente (o la primera si todas resueltas).
  const [index, setIndex] = useState(() => {
    const i = questions.findIndex((q) => statusOf(q.id) === "pendiente");
    return i === -1 ? 0 : i;
  });

  const total = questions.length;
  const answered = questions.filter((q) => statusOf(q.id) !== "pendiente").length;
  const current = questions[Math.min(index, total - 1)];
  const status = statusOf(current.id);

  const goNext = () => setIndex((i) => Math.min(i + 1, total - 1));
  const goPrev = () => setIndex((i) => Math.max(i - 1, 0));

  const pct = total > 0 ? Math.round((answered / total) * 100) : 0;
  const allDone = answered >= total;

  return (
    <>
      <SheetHeader>
        <div className="flex items-center gap-2 pr-8">
          <SheetTitle>{title}</SheetTitle>
        </div>
        <div className="mt-1.5 flex items-center gap-2 text-[11px] text-meta-foreground">
          <span className="tabular-nums">
            {answered} de {total} respondidas
          </span>
          {allDone && (
            <span className="inline-flex items-center gap-1 font-medium text-emerald-600">
              <CheckCircle2 className="h-3.5 w-3.5" /> completo
            </span>
          )}
        </div>
        {/* Barra de progreso */}
        <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-muted">
          <div
            className={cn(
              "h-full rounded-full transition-[width] duration-300 ease-out",
              allDone ? "bg-emerald-500" : "bg-primary",
            )}
            style={{ width: `${pct}%` }}
          />
        </div>
      </SheetHeader>

      <SheetBody>
        <div className="mb-3 flex items-center justify-between text-[11px] text-meta-foreground">
          <span className="tabular-nums">
            Pregunta {Math.min(index, total - 1) + 1} de {total}
          </span>
          <Badge
            variant="outline"
            className={cn(
              status === "confirmado" && "border-emerald-300 bg-emerald-50 text-emerald-700",
              status === "corregido" && "border-amber-300 bg-amber-50 text-amber-700",
              status === "pendiente" && "border-slate-300 bg-slate-50 text-slate-600",
            )}
          >
            {STATUS_LABEL[status]}
          </Badge>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <span className="inline-flex items-center rounded-md border border-border/60 bg-muted/50 px-1.5 py-0.5 font-mono text-[11px] leading-none text-meta-foreground">
            {current.id}
          </span>
          {current.audience && <AudienceBadge audience={current.audience} />}
          {current.blocking && <Badge className="bg-red-600">bloqueante</Badge>}
          {current.linked_to_ref && (
            <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
              ligada a <RefChip refId={current.linked_to_ref} />
            </span>
          )}
        </div>

        <p className="mt-3 text-[15px] font-medium leading-relaxed">
          {current.question}
        </p>
        {current.reason && (
          <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">
            Motivo: {current.reason}
          </p>
        )}

        <div className="mt-4">{renderControls(current, goNext)}</div>
      </SheetBody>

      <SheetFooter>
        <Button
          variant="outline"
          size="sm"
          className="gap-1"
          onClick={goPrev}
          disabled={index <= 0}
        >
          <ChevronLeft className="h-3.5 w-3.5" />
          Anterior
        </Button>
        <span className="mx-auto text-[11px] tabular-nums text-meta-foreground">
          {Math.min(index, total - 1) + 1} / {total}
        </span>
        <Button
          variant="outline"
          size="sm"
          className="gap-1"
          onClick={goNext}
          disabled={index >= total - 1}
        >
          Siguiente
          <ChevronRight className="h-3.5 w-3.5" />
        </Button>
      </SheetFooter>
    </>
  );
}
