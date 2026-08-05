"use client";

// Controles de validación del Analista. Adaptador fino sobre el control
// compartido (`components/artifact/validation-controls.tsx`): aquí solo vive a qué
// endpoint se escribe. El EF es el único que valida `assumption` además de
// `question`, de ahí el `targetType`.

import { ArtifactValidationControls } from "@/components/artifact/validation-controls";
import { efApi } from "@/lib/api/ef";
import type { QuestionStatus } from "@/lib/types/ef";

export function ValidationControls({
  jobId,
  targetType,
  targetId,
  status,
  respuesta,
  onChanged,
  readOnly = false,
}: {
  jobId: string;
  targetType: "question" | "assumption";
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
      roleLabel="Analista"
      onSubmit={(id, nuevoEstado, texto) =>
        efApi.patchValidation(jobId, {
          target_type: targetType,
          target_id: id,
          status: nuevoEstado,
          respuesta: texto,
        })
      }
    />
  );
}
