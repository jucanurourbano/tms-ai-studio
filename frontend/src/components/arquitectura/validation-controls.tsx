"use client";

import { Check, Pencil } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { arquitecturaApi } from "@/lib/api/arquitectura";
import { ApiError } from "@/lib/api/client";
import type { QuestionStatus } from "@/lib/types/ef";

const STATUS_STYLE: Record<QuestionStatus, string> = {
  pendiente: "border-slate-300 bg-slate-50 text-slate-600",
  confirmado: "border-emerald-300 bg-emerald-50 text-emerald-700",
  corregido: "border-amber-300 bg-amber-50 text-amber-700",
};

/** Controles de validación del Arquitecto (mismo patrón que EF/Scrum). */
export function ArchitectValidationControls({
  jobId,
  targetId,
  status,
  respuesta,
  onChanged,
}: {
  jobId: string;
  targetId: string;
  status: QuestionStatus;
  respuesta?: string | null;
  onChanged: () => void;
}) {
  const [comment, setComment] = useState(respuesta ?? "");
  const [submitting, setSubmitting] = useState(false);

  async function submit(newStatus: "confirmado" | "corregido") {
    if (newStatus === "corregido" && comment.trim().length === 0) {
      toast.error("Escribe la respuesta antes de guardar.");
      return;
    }
    setSubmitting(true);
    try {
      await arquitecturaApi.patchValidation(jobId, {
        target_type: "question",
        target_id: targetId,
        status: newStatus,
        respuesta: comment.trim() || null,
      });
      toast.success(
        newStatus === "confirmado" ? "Confirmado" : "Respuesta registrada",
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

  return (
    <div className="mt-2 rounded-md border bg-muted/30 p-2 space-y-2">
      <div className="flex items-center gap-2">
        <span className="text-[11px] text-muted-foreground">
          Estado (Arquitecto):
        </span>
        <Badge variant="outline" className={STATUS_STYLE[status]}>
          {status}
        </Badge>
      </div>
      <Textarea
        value={comment}
        onChange={(e) => setComment(e.target.value)}
        rows={2}
        placeholder="Respuesta del Arquitecto / Líder Técnico…"
        className="text-xs"
      />
      <div className="flex gap-2">
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
        <Button
          size="sm"
          variant="outline"
          className="gap-1.5 border-amber-300 text-amber-700 hover:bg-amber-50"
          disabled={submitting}
          onClick={() => submit("corregido")}
        >
          <Pencil className="h-3.5 w-3.5" />
          Responder
        </Button>
      </div>
    </div>
  );
}
