"use client";

// CONTROLES DE VALIDACIÓN compartidos por todos los agentes del ISDF.
//
// Los cuatro agentes (EF, Scrum, Arquitectura, BD) responden preguntas igual: una
// caja de texto y dos botones. Lo único que cambia es a qué endpoint se escribe y
// cómo se llama el rol que responde, así que eso se inyecta y el resto —incluida
// la parte difícil, que es explicar la diferencia entre los dos botones— vive aquí
// una sola vez.
//
// **Confirmar vs Corregir** es la decisión que más se malinterpreta del ciclo de
// afinamiento, y no es cosmética: alimenta el contexto autoritativo del refine.
//   · Confirmar = la observación del agente es válida y aportas el dato que
//     faltaba.
//   · Corregir = el agente entendió mal y rectificas su interpretación.
// Se explica en tres sitios con coste creciente de atención: tooltip (a demanda),
// microcopy permanente bajo la caja (a la vista) y un hint descartable la primera
// vez (imposible de no ver, una sola vez).
//
// **El texto está aislado por pregunta** (`lib/validation-draft.ts`). No es un
// detalle: sin ese aislamiento el texto de una pregunta se guardaba en la
// siguiente. Ver el módulo para el caso real que lo provocó.
//
// **Los dos botones exigen texto** y están deshabilitados mientras la caja esté
// vacía: un "confirmado" en blanco no aporta nada al refine, que es justo para lo
// que sirve responder.

import { Check, Info, Pencil, RotateCcw, Save, X } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { ValidationReadOnly } from "@/components/artifact/validation-readonly";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { ApiError } from "@/lib/api/client";
import type { QuestionStatus } from "@/lib/types/ef";
import { usePersistentState } from "@/lib/use-persistent-state";
import { cn } from "@/lib/utils";
import { draftFor, syncDraft } from "@/lib/validation-draft";

const STATUS_STYLE: Record<QuestionStatus, string> = {
  pendiente: "border-slate-300 bg-slate-50 text-slate-600",
  confirmado: "border-emerald-300 bg-emerald-50 text-emerald-700",
  corregido: "border-amber-300 bg-amber-50 text-amber-700",
};

export const CONFIRM_HELP =
  "La observación es válida: registro la respuesta o el dato que faltaba.";
export const CORRECT_HELP = "El agente entendió mal: registro la corrección.";
const EMPTY_HELP = "Escribe la respuesta o corrección antes de continuar.";

/** Clave del hint de bienvenida: se descarta una vez y no vuelve. */
const HINT_KEY = "artifact:validation-hint-dismissed";

/**
 * Hint de dos líneas que explica los dos botones. Se muestra **una vez** por
 * navegador y se descarta a mano; a partir de ahí el microcopy permanente basta.
 */
export function ValidationHint() {
  const [dismissed, setDismissed] = usePersistentState(HINT_KEY, false);
  if (dismissed) return null;

  return (
    <div className="mb-3 flex items-start gap-2 rounded-lg border border-sky-200 bg-sky-50/60 p-3 text-xs leading-relaxed text-sky-900 print:hidden">
      <Info className="mt-0.5 h-4 w-4 shrink-0 text-sky-600" />
      <div className="min-w-0 flex-1">
        <p>
          <b>Confirmar</b> cuando la observación del agente es válida y solo falta
          el dato: tu respuesta se añade como contexto.
        </p>
        <p>
          <b>Corregir</b> cuando el agente entendió mal: tu texto rectifica su
          interpretación en la próxima versión.
        </p>
      </div>
      <button
        type="button"
        onClick={() => setDismissed(true)}
        aria-label="Descartar la explicación"
        className="shrink-0 rounded p-0.5 text-sky-700/70 transition-colors hover:bg-sky-100 hover:text-sky-900"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}

export function ArtifactValidationControls({
  targetId,
  status,
  respuesta,
  onChanged,
  onSubmit,
  roleLabel,
  readOnly = false,
}: {
  targetId: string;
  status: QuestionStatus;
  respuesta?: string | null;
  /** Se llama tras guardar con éxito (recarga el resumen y avanza el flujo). */
  onChanged: () => void;
  /** Escritura real contra el agente correspondiente. */
  onSubmit: (
    targetId: string,
    status: QuestionStatus,
    respuesta: string | null,
  ) => Promise<unknown>;
  /** Quién responde en este agente: "Analista", "PO", "Arquitecto", "DBA". */
  roleLabel: string;
  /** Modo lectura: se muestra el estado, sin controles de escritura. */
  readOnly?: boolean;
}) {
  const [draft, setDraft] = useState(() => draftFor(targetId, respuesta));
  const [submitting, setSubmitting] = useState(false);

  // Ajuste de estado durante el render (patrón oficial de React): si cambió la
  // pregunta —o su respuesta guardada— el borrador se rehace. Hacerlo aquí y no
  // en un efecto evita pintar un fotograma con el texto de la pregunta anterior,
  // que es exactamente lo que confundía a quien respondía rápido.
  const sincronizado = syncDraft(draft, targetId, respuesta);
  if (sincronizado) setDraft(sincronizado);
  const texto = (sincronizado ?? draft).text;

  const answered = status !== "pendiente";
  const vacio = texto.trim().length === 0;

  async function guardar(nuevoEstado: QuestionStatus) {
    if (nuevoEstado !== "pendiente" && texto.trim().length === 0) {
      toast.error(EMPTY_HELP);
      return;
    }
    setSubmitting(true);
    try {
      const cuerpo = nuevoEstado === "pendiente" ? null : texto.trim();
      await onSubmit(targetId, nuevoEstado, cuerpo);
      toast.success(
        nuevoEstado === "pendiente"
          ? "Respuesta borrada: la pregunta vuelve a estar pendiente"
          : nuevoEstado === "confirmado"
            ? "Confirmado"
            : "Corrección registrada",
      );
      onChanged();
    } catch (err) {
      toast.error("No se pudo guardar", {
        description: err instanceof ApiError ? err.message : undefined,
      });
    } finally {
      setSubmitting(false);
    }
  }

  // Sin permiso de edición en el módulo: mismo estado, sin acciones.
  if (readOnly) {
    return <ValidationReadOnly status={status} respuesta={respuesta} />;
  }

  return (
    <div className="mt-2 space-y-2 rounded-md border bg-muted/30 p-2">
      <div className="flex items-center gap-2">
        <span className="text-[11px] text-muted-foreground">
          Estado ({roleLabel}):
        </span>
        <Badge variant="outline" className={STATUS_STYLE[status]}>
          {status}
        </Badge>
      </div>
      <Textarea
        // `key` por pregunta: además del borrador derivado, garantiza que el DOM
        // del textarea (cursor, scroll, selección) no se herede entre preguntas.
        key={targetId}
        value={texto}
        onChange={(e) =>
          setDraft({ targetId, source: respuesta ?? "", text: e.target.value })
        }
        rows={2}
        placeholder={`Respuesta del ${roleLabel}…`}
        className="text-xs"
      />
      <p className="text-[11px] leading-relaxed text-muted-foreground">
        {vacio ? (
          <span className="text-amber-700">{EMPTY_HELP}</span>
        ) : (
          <>
            Confirmar = aportas el dato faltante · Corregir = rectificas una
            interpretación errónea
          </>
        )}
      </p>

      {answered ? (
        // Ya respondida: el gesto natural es **editar**, no volver a confirmar.
        <div className="flex flex-wrap gap-2">
          <ActionButton
            help="Guarda el texto corregido manteniendo el estado actual."
            disabled={submitting || vacio}
            onClick={() => guardar(status)}
            className="border-sky-300 text-sky-700 hover:bg-sky-50"
            icon={<Save className="h-3.5 w-3.5" />}
            label="Actualizar respuesta"
          />
          <ActionButton
            help="Borra la respuesta y deja la pregunta pendiente otra vez."
            disabled={submitting}
            onClick={() => guardar("pendiente")}
            className="text-muted-foreground"
            icon={<RotateCcw className="h-3.5 w-3.5" />}
            label="Volver a pendiente"
          />
        </div>
      ) : (
        <div className="flex flex-wrap gap-2">
          <ActionButton
            help={vacio ? EMPTY_HELP : CONFIRM_HELP}
            disabled={submitting || vacio}
            onClick={() => guardar("confirmado")}
            className="border-emerald-300 text-emerald-700 hover:bg-emerald-50"
            icon={<Check className="h-3.5 w-3.5" />}
            label="Confirmar"
          />
          <ActionButton
            help={vacio ? EMPTY_HELP : CORRECT_HELP}
            disabled={submitting || vacio}
            onClick={() => guardar("corregido")}
            className="border-amber-300 text-amber-700 hover:bg-amber-50"
            icon={<Pencil className="h-3.5 w-3.5" />}
            label="Corregir"
          />
        </div>
      )}
    </div>
  );
}

/**
 * Botón con tooltip que **sigue explicándose cuando está deshabilitado**.
 *
 * Un botón deshabilitado no recibe eventos de puntero, así que el tooltip moriría
 * justo cuando más falta hace: cuando el usuario no entiende por qué no puede
 * pulsarlo. El envoltorio recibe el hover en su lugar.
 */
function ActionButton({
  help,
  disabled,
  onClick,
  className,
  icon,
  label,
}: {
  help: string;
  disabled: boolean;
  onClick: () => void;
  className?: string;
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <Tooltip>
      <TooltipTrigger
        // El disparador es el envoltorio, no el botón: un botón deshabilitado no
        // recibe eventos de puntero y el tooltip se perdería justo cuando hace
        // falta. Misma forma que `OriginBadge` en `ef/badges.tsx`.
        render={
          <span className="inline-flex">
            <Button
              size="sm"
              variant="outline"
              className={cn("gap-1.5", className)}
              disabled={disabled}
              onClick={onClick}
            >
              {icon}
              {label}
            </Button>
          </span>
        }
      />
      <TooltipContent>{help}</TooltipContent>
    </Tooltip>
  );
}
