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
// **Los dos botones exigen texto.** Antes se podía confirmar en blanco, y un
// "confirmado" sin contenido no aporta nada al refine: el job hijo recibe una
// respuesta vacía y vuelve a preguntar lo mismo.

import { Check, Info, Pencil, X } from "lucide-react";
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

const STATUS_STYLE: Record<QuestionStatus, string> = {
  pendiente: "border-slate-300 bg-slate-50 text-slate-600",
  confirmado: "border-emerald-300 bg-emerald-50 text-emerald-700",
  corregido: "border-amber-300 bg-amber-50 text-amber-700",
};

export const CONFIRM_HELP =
  "La observación es válida: registro la respuesta o el dato que faltaba.";
export const CORRECT_HELP =
  "El agente entendió mal: registro la corrección.";

/** Clave del hint de bienvenida: se descarta una vez y no vuelve. */
const HINT_KEY = "artifact:validation-hint-dismissed";

/**
 * Hint de dos líneas que explica los dos botones. Se muestra **una vez** por
 * navegador y se descarta a mano; a partir de ahí el microcopy permanente basta.
 *
 * Se renderiza al principio de la sección de preguntas (en ambos modos), no por
 * pregunta: repetirlo en cada fila de la lista sería ruido.
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
    status: "confirmado" | "corregido",
    respuesta: string,
  ) => Promise<unknown>;
  /** Quién responde en este agente: "Analista", "PO", "Arquitecto", "DBA". */
  roleLabel: string;
  /** Modo lectura: se muestra el estado, sin controles de escritura. */
  readOnly?: boolean;
}) {
  const [comment, setComment] = useState(respuesta ?? "");
  const [submitting, setSubmitting] = useState(false);

  async function submit(newStatus: "confirmado" | "corregido") {
    // Ambos botones exigen texto: un "confirmado" en blanco no aporta nada al
    // refine, que es justo para lo que sirve responder.
    if (comment.trim().length === 0) {
      toast.error("Escribe la respuesta o corrección antes de continuar.");
      return;
    }
    setSubmitting(true);
    try {
      await onSubmit(targetId, newStatus, comment.trim());
      toast.success(
        newStatus === "confirmado" ? "Confirmado" : "Corrección registrada",
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
        value={comment}
        onChange={(e) => setComment(e.target.value)}
        rows={2}
        placeholder={`Respuesta del ${roleLabel}…`}
        className="text-xs"
      />
      <p className="text-[11px] leading-relaxed text-muted-foreground">
        Confirmar = aportas el dato faltante · Corregir = rectificas una
        interpretación errónea
      </p>
      <div className="flex gap-2">
        <Tooltip>
          <TooltipTrigger
            render={
              <Button
                size="sm"
                variant="outline"
                className="gap-1.5 border-emerald-300 text-emerald-700 hover:bg-emerald-50"
                disabled={submitting}
                onClick={() => submit("confirmado")}
              >
                <Check className="h-3.5 w-3.5" />
                Confirmar
              </Button>
            }
          />
          <TooltipContent>{CONFIRM_HELP}</TooltipContent>
        </Tooltip>
        <Tooltip>
          <TooltipTrigger
            render={
              <Button
                size="sm"
                variant="outline"
                className="gap-1.5 border-amber-300 text-amber-700 hover:bg-amber-50"
                disabled={submitting}
                onClick={() => submit("corregido")}
              >
                <Pencil className="h-3.5 w-3.5" />
                Corregir
              </Button>
            }
          />
          <TooltipContent>{CORRECT_HELP}</TooltipContent>
        </Tooltip>
      </div>
    </div>
  );
}
