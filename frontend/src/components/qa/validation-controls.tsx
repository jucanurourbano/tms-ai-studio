"use client";

// Controles de validación del QA lead. Adaptador fino sobre el control
// compartido (`components/artifact/validation-controls.tsx`).

import { ArtifactValidationControls } from "@/components/artifact/validation-controls";
import { qaApi } from "@/lib/api/qa";
import type { QuestionStatus } from "@/lib/types/ef";

export function QaLeadValidationControls({
  jobId,
  targetId,
  status,
  respuesta,
  onChanged,
  readOnly = false,
}: {
  jobId: string;
  targetId: string;
  status: QuestionStatus;
  respuesta?: string | null;
  onChanged: () => void;
  /** Modo lectura: se muestra el estado, sin controles de escritura. */
  readOnly?: boolean;
}) {
  return (
    <ArtifactValidationControls
      targetId={targetId}
      status={status}
      respuesta={respuesta}
      onChanged={onChanged}
      readOnly={readOnly}
      roleLabel="QA lead"
      onSubmit={(id, nuevoEstado, texto) =>
        qaApi.patchValidation(jobId, {
          target_type: "question",
          target_id: id,
          status: nuevoEstado,
          respuesta: texto,
        })
      }
    />
  );
}
