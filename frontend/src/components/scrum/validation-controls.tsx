"use client";

// Controles de validación del Product Owner. Adaptador fino sobre el control
// compartido (`components/artifact/validation-controls.tsx`).

import { ArtifactValidationControls } from "@/components/artifact/validation-controls";
import { scrumApi } from "@/lib/api/scrum";
import type { QuestionStatus } from "@/lib/types/ef";

export function ScrumValidationControls({
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
      roleLabel="PO"
      onSubmit={(id, nuevoEstado, texto) =>
        scrumApi.patchValidation(jobId, {
          target_type: "question",
          target_id: id,
          status: nuevoEstado,
          respuesta: texto,
        })
      }
    />
  );
}
