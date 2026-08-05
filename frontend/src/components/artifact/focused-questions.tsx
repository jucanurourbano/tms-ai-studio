"use client";

// MODO ENFOCADO para responder preguntas de afinamiento: una pregunta a la vez,
// con su contexto, barra de progreso y **avance automático al responder**.
//
// Vive como bloque dentro del panel lateral universal, en la sección "Preguntas".
// El usuario no distingue dos paneles distintos, solo dos formas de mirar la misma
// sección — lista o una a una.
//
// El avance automático salta a la siguiente pregunta **pendiente**, no a la
// siguiente por orden: responder no debe obligar a pasar por encima de las ya
// resueltas. Cuando no queda ninguna, el flujo no se queda mirando la última
// respondida — cierra con un estado de cierre que dice cómo quedó el semáforo y
// ofrece el paso siguiente del agente. Si ese agente no tiene un paso siguiente
// que ofrecer, el panel se cierra solo: el trabajo terminó y dejar una pantalla
// muerta abierta es peor que quitarla de en medio.

import { CheckCircle2, ChevronLeft, ChevronRight } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { RefChip } from "@/components/artifact/primitives";
import { AudienceBadge } from "@/components/ef/badges";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  initialQuestionIndex,
  nextPendingIndex,
} from "@/lib/focused-questions";
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

/** Acción propia del agente tras terminar (regenerar, pasar al siguiente…). */
export interface NextStepAction {
  label: string;
  onClick: () => void;
  /** Texto corto que explica qué hará (aparece bajo el botón). */
  hint?: string;
}

const STATUS_LABEL: Record<QuestionStatus, string> = {
  pendiente: "Pendiente",
  confirmado: "Confirmada",
  corregido: "Corregida",
};

/** Espera antes de cerrar solo, cuando no hay acción siguiente que ofrecer. */
const AUTO_CLOSE_MS = 1500;

export function FocusedQuestionFlow({
  questions,
  statusOf,
  renderControls,
  ready = false,
  readyLabel,
  nextAction,
  onClose,
}: {
  questions: SheetQuestion[];
  statusOf: (id: string) => QuestionStatus;
  /** Controles de validación del agente; llama a `onAnswered` al guardar. */
  renderControls: (q: SheetQuestion, onAnswered: () => void) => React.ReactNode;
  /** Semáforo del artefacto tras responder (lo pinta el estado de cierre). */
  ready?: boolean;
  /** Qué habilita el semáforo verde: "Listo para el Agente Scrum". */
  readyLabel?: string;
  /** Paso siguiente del agente. Sin él, el panel se cierra solo al terminar. */
  nextAction?: NextStepAction;
  /** Cierra el panel lateral. */
  onClose?: () => void;
}) {
  const [index, setIndex] = useState(() =>
    initialQuestionIndex(questions, statusOf),
  );
  // Estado de cierre: se enciende al responder la ÚLTIMA pendiente, no con solo
  // llegar al final. Así abrir un artefacto ya completo no lanza la celebración.
  const [finished, setFinished] = useState(false);
  // Micro-transición: la tarjeta se atenúa un instante al saltar de pregunta.
  const [advancing, setAdvancing] = useState(false);
  // Latido del contador al incrementarse: confirma que la respuesta se guardó.
  const [bumping, setBumping] = useState(false);

  const total = questions.length;
  const answered = questions.filter((q) => statusOf(q.id) !== "pendiente").length;

  /** Salta a la siguiente pendiente. Devuelve `false` si ya no queda ninguna. */
  const goToNextPending = useCallback(
    (from: number) => {
      const target = nextPendingIndex(questions, statusOf, from);
      if (target === null) return false;
      setAdvancing(true);
      setIndex(target);
      return true;
    },
    [questions, statusOf],
  );

  // El fundido dura lo mismo que la transición del contenedor.
  useEffect(() => {
    if (!advancing) return;
    const t = setTimeout(() => setAdvancing(false), 180);
    return () => clearTimeout(t);
  }, [advancing]);

  // El contador late cuando sube (no en el primer render ni al bajar por un
  // "volver a pendiente"): es la confirmación visual de que se guardó.
  const answeredRef = useRef(answered);
  useEffect(() => {
    const subio = answered > answeredRef.current;
    answeredRef.current = answered;
    if (!subio) return;
    setBumping(true);
    const t = setTimeout(() => setBumping(false), 220);
    return () => clearTimeout(t);
  }, [answered]);

  // Sin acción siguiente que ofrecer, el estado de cierre se despide solo.
  // `onClose` es estable (`useCallback` del hub) y, cuando este efecto aplica,
  // `nextAction` es `undefined`: el temporizador no se reinicia en cada render.
  useEffect(() => {
    if (!finished || nextAction || !onClose) return;
    const t = setTimeout(onClose, AUTO_CLOSE_MS);
    return () => clearTimeout(t);
  }, [finished, nextAction, onClose]);

  if (questions.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No hay preguntas para responder.
      </p>
    );
  }

  const position = Math.min(index, total - 1);
  const current = questions[position];
  const status = statusOf(current.id);
  const pct = Math.round((answered / total) * 100);
  const allDone = answered >= total;

  /**
   * Se llamó tras guardar una respuesta: avanzar a la siguiente pendiente o, si
   * era la última, mostrar el cierre.
   */
  const handleAnswered = () => {
    if (!goToNextPending(position)) setFinished(true);
  };

  const goNext = () => setIndex((i) => Math.min(i + 1, total - 1));
  const goPrev = () => setIndex((i) => Math.max(i - 1, 0));

  if (finished) {
    return (
      <CompletionState
        total={total}
        ready={ready}
        readyLabel={readyLabel}
        nextAction={nextAction}
        onClose={onClose}
        onReview={() => {
          setFinished(false);
          setIndex(0);
        }}
      />
    );
  }

  return (
    <div className="flex min-h-full flex-col">
      {/* Progreso: la cifra manda. Ver subir el contador es la señal de que la
          respuesta se guardó y de que quedan menos. */}
      <div className="mb-4">
        <div className="flex items-end gap-2">
          <span
            className={cn(
              "font-heading text-3xl font-semibold leading-none tabular-nums transition-transform duration-200",
              bumping && "scale-125 text-emerald-600",
              allDone && "text-emerald-600",
            )}
          >
            {answered}
          </span>
          <span className="pb-0.5 text-sm text-muted-foreground">
            de {total} respondidas
          </span>
          {allDone && (
            <span className="inline-flex items-center gap-1 pb-0.5 text-sm font-medium text-emerald-600">
              <CheckCircle2 className="h-4 w-4" /> completo
            </span>
          )}
          <span className="ml-auto pb-0.5 text-[11px] tabular-nums text-meta-foreground">
            viendo {position + 1} de {total}
          </span>
        </div>
        <div className="mt-2 h-2 overflow-hidden rounded-full bg-muted">
          <div
            className={cn(
              "h-full rounded-full transition-[width] duration-500 ease-out",
              allDone ? "bg-emerald-500" : "bg-primary",
            )}
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>

      <div
        className={cn(
          "rounded-xl border p-4 transition-opacity duration-150 motion-reduce:transition-none",
          advancing ? "opacity-0" : "opacity-100",
        )}
      >
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

        {/* `key` por pregunta: aunque el control ya aísla su borrador, remontarlo
            impide que CUALQUIER estado interno viaje entre preguntas. Es barato y
            este bug ya corrompió datos una vez. */}
        <div key={current.id} className="mt-4">
          {renderControls(current, handleAnswered)}
        </div>
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
        <ProgressDots
          questions={questions}
          statusOf={statusOf}
          position={position}
          onJump={setIndex}
        />
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

/** Cierre del afinamiento: qué se consiguió y qué se puede hacer ahora. */
function CompletionState({
  total,
  ready,
  readyLabel,
  nextAction,
  onClose,
  onReview,
}: {
  total: number;
  ready: boolean;
  readyLabel?: string;
  nextAction?: NextStepAction;
  onClose?: () => void;
  onReview: () => void;
}) {
  return (
    <div className="flex min-h-full flex-col items-center justify-center py-10 text-center">
      <div className="animate-celebrate rounded-full bg-emerald-50 p-3">
        <CheckCircle2 className="h-8 w-8 text-emerald-600" />
      </div>
      <p className="mt-4 font-heading text-lg font-semibold">
        Todas las preguntas respondidas
      </p>
      <p className="mt-1 text-sm text-muted-foreground">
        {total === 1 ? "1 pregunta resuelta" : `${total} preguntas resueltas`}.
      </p>

      <span
        className={cn(
          "mt-4 inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs",
          ready
            ? "border-emerald-300 bg-emerald-50 text-emerald-700"
            : "border-slate-300 bg-slate-50 text-slate-600",
        )}
      >
        <span
          className={cn(
            "h-2 w-2 rounded-full",
            ready ? "bg-emerald-500" : "bg-slate-400",
          )}
        />
        {ready
          ? (readyLabel ?? "Listo para la siguiente etapa")
          : "El semáforo sigue pendiente de otros requisitos"}
      </span>

      {!ready && (
        // Los semáforos compuestos no dependen solo de las preguntas: decirlo
        // aquí evita que el verde parezca roto.
        <p className="mt-2 max-w-xs text-xs text-muted-foreground">
          Responder las preguntas no era lo único que faltaba. Revisa el análisis
          del artefacto para ver qué queda.
        </p>
      )}

      <div className="mt-6 flex flex-wrap items-center justify-center gap-2">
        {onClose && (
          <Button variant="outline" size="sm" onClick={onClose}>
            Cerrar
          </Button>
        )}
        {nextAction && (
          <Button size="sm" onClick={nextAction.onClick}>
            {nextAction.label}
          </Button>
        )}
      </div>
      {nextAction?.hint && (
        <p className="mt-2 max-w-xs text-[11px] text-muted-foreground">
          {nextAction.hint}
        </p>
      )}

      <button
        type="button"
        onClick={onReview}
        className="mt-4 text-xs text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
      >
        Volver a revisar las respuestas
      </button>
    </div>
  );
}

/**
 * Puntos de progreso: una pregunta, un punto. Sustituyen al "3 / 16" porque
 * dicen dos cosas que el número no dice — **cuáles** quedan por responder y dónde
 * está uno— y permiten saltar directamente a cualquiera.
 *
 * Con muchas preguntas los puntos se encogen en vez de desbordar el panel: perder
 * grosor es aceptable, perder la fila entera no.
 */
function ProgressDots({
  questions,
  statusOf,
  position,
  onJump,
}: {
  questions: SheetQuestion[];
  statusOf: (id: string) => QuestionStatus;
  position: number;
  onJump: (index: number) => void;
}) {
  return (
    <div className="mx-auto flex min-w-0 flex-1 flex-wrap items-center justify-center gap-1 px-2">
      {questions.map((q, i) => {
        const estado = statusOf(q.id);
        const actual = i === position;
        return (
          <button
            key={q.id}
            type="button"
            onClick={() => onJump(i)}
            title={`${q.id} · ${STATUS_LABEL[estado]}`}
            aria-label={`Ir a ${q.id}, ${STATUS_LABEL[estado]}`}
            aria-current={actual ? "step" : undefined}
            className={cn(
              "h-2 w-2 shrink-0 rounded-full transition-all duration-200",
              estado === "pendiente"
                ? "bg-muted-foreground/25 hover:bg-muted-foreground/50"
                : estado === "corregido"
                  ? "bg-amber-500/70 hover:bg-amber-500"
                  : "bg-emerald-500/70 hover:bg-emerald-500",
              // La actual se distingue por tamaño y anillo, no solo por color: el
              // color ya está ocupado diciendo el estado.
              actual && "h-2.5 w-2.5 ring-2 ring-primary/40 ring-offset-1",
            )}
          />
        );
      })}
    </div>
  );
}
