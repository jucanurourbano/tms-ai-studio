"use client";

// Controles de validación del DBA. Adaptador fino sobre el control compartido
// (`components/artifact/validation-controls.tsx`).

import { ArtifactValidationControls } from "@/components/artifact/validation-controls";
import { bdApi } from "@/lib/api/bd";
import type { QuestionStatus } from "@/lib/types/ef";

export function DbaValidationControls({
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
      roleLabel="DBA"
      onSubmit={(id, nuevoEstado, texto) =>
        bdApi.patchValidation(jobId, {
          target_type: "question",
          target_id: id,
          status: nuevoEstado,
          respuesta: texto,
        })
      }
    />
  );
}
