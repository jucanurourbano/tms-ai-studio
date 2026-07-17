"use client";

import { useEffect, useRef, useState } from "react";

import { JobStatusBadge, Mono } from "@/components/ef/badges";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { efApi } from "@/lib/api/ef";
import type { JobDetail, JobStatus } from "@/lib/types/ef";

const TERMINAL: JobStatus[] = ["COMPLETED", "COMPLETED_WITH_WARNINGS", "FAILED"];

const PHASES = [
  "INGEST",
  "PARSE",
  "SEGMENT",
  "EXTRACT",
  "CONSOLIDATE",
  "INFER",
  "INTERPRET",
  "CRITIQUE",
  "QUESTION_GEN",
  "ASSEMBLE",
  "PERSIST",
];

export function ProgressView({
  job,
  onUpdate,
}: {
  job: JobDetail;
  onUpdate: (job: JobDetail) => void;
}) {
  const [elapsed, setElapsed] = useState(0);
  const startRef = useRef<number | null>(null);

  // Cronómetro (desde que se abrió la vista). Date.now() se llama en el efecto,
  // no durante el render.
  useEffect(() => {
    startRef.current = Date.now();
    const t = setInterval(() => {
      const start = startRef.current ?? Date.now();
      setElapsed(Math.floor((Date.now() - start) / 1000));
    }, 1000);
    return () => clearInterval(t);
  }, []);

  // Polling del estado del job cada 5s hasta que sea terminal.
  useEffect(() => {
    if (TERMINAL.includes(job.status)) return;
    const t = setInterval(async () => {
      try {
        const updated = await efApi.getJob(job.job_id);
        onUpdate(updated);
      } catch {
        // silencioso; el siguiente tick reintenta
      }
    }, 5000);
    return () => clearInterval(t);
  }, [job.job_id, job.status, onUpdate]);

  return (
    <div className="p-6 max-w-3xl space-y-4">
      <header>
        <h1 className="text-xl font-heading font-semibold">
          Análisis en proceso
        </h1>
        <div className="mt-1 flex items-center gap-3 text-sm text-muted-foreground">
          <Mono>{job.job_id}</Mono>
          <JobStatusBadge status={job.status} />
          <span>{elapsed}s (desde que abriste la vista)</span>
        </div>
      </header>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Pipeline (progreso global)</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="h-1.5 w-full overflow-hidden rounded bg-muted">
            <div className="h-full w-1/3 animate-pulse rounded bg-blue-500" />
          </div>
          <p className="text-xs text-muted-foreground">
            El avance por fase es aspiracional: el backend reporta un estado
            global, por lo que el progreso se muestra indeterminado.
          </p>
          <ol className="grid grid-cols-2 gap-x-6 gap-y-1 sm:grid-cols-3">
            {PHASES.map((phase, i) => (
              <li
                key={phase}
                className="flex items-center gap-2 text-xs text-muted-foreground"
              >
                <span className="inline-block h-1.5 w-1.5 rounded-full bg-muted-foreground/40" />
                <Mono>{phase}</Mono>
                {i === 0 && <span className="text-[10px]">(inicio)</span>}
                {i === PHASES.length - 1 && (
                  <span className="text-[10px]">(fin)</span>
                )}
              </li>
            ))}
          </ol>
        </CardContent>
      </Card>

      <p className="text-xs text-muted-foreground">
        Actualizando estado automáticamente cada 5 segundos…
      </p>
    </div>
  );
}
