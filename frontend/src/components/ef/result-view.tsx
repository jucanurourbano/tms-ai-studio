"use client";

// Vista de Resultado — versión mínima (F2). La vista completa de dos columnas
// (índice + afinamiento) se implementa en F3.

import { JobStatusBadge, Mono } from "@/components/ef/badges";
import type { JobDetail } from "@/lib/types/ef";

export function ResultView({ job }: { job: JobDetail }) {
  return (
    <div className="p-6 max-w-3xl space-y-3">
      <header>
        <h1 className="text-xl font-heading font-semibold">
          Resultado del análisis
        </h1>
        <div className="mt-1 flex items-center gap-3 text-sm text-muted-foreground">
          <Mono>{job.job_id}</Mono>
          <JobStatusBadge status={job.status} />
        </div>
      </header>
      <p className="text-sm text-muted-foreground">
        La vista completa del EFArtifact (interpretación, preguntas, requisitos,
        modelo y afinamiento) se implementa en la fase F3.
      </p>
    </div>
  );
}
