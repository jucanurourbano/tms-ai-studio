"use client";

import { useEffect, useRef, useState } from "react";

import { JobStatusBadge, Mono } from "@/components/ef/badges";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { scrumApi } from "@/lib/api/scrum";
import type { JobStatus } from "@/lib/types/ef";
import type { ScrumJobDetail } from "@/lib/types/scrum";

const TERMINAL: JobStatus[] = ["COMPLETED", "COMPLETED_WITH_WARNINGS", "FAILED"];

const PHASES = [
  "LOAD_EF",
  "EPICS",
  "STORIES",
  "CRITERIA",
  "ESTIMATE",
  "PRIORITIZE",
  "SPRINT_PLAN",
  "CRITIQUE",
  "QUESTION_GEN",
  "ASSEMBLE",
  "PERSIST",
];

export function ScrumProgressView({
  job,
  onUpdate,
}: {
  job: ScrumJobDetail;
  onUpdate: (job: ScrumJobDetail) => void;
}) {
  const [elapsed, setElapsed] = useState(0);
  const startRef = useRef<number | null>(null);

  useEffect(() => {
    startRef.current = Date.now();
    const t = setInterval(() => {
      const start = startRef.current ?? Date.now();
      setElapsed(Math.floor((Date.now() - start) / 1000));
    }, 1000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    if (TERMINAL.includes(job.status)) return;
    const t = setInterval(async () => {
      try {
        const updated = await scrumApi.getJob(job.job_id);
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
          Planificación en proceso
        </h1>
        <div className="mt-1 flex items-center gap-3 text-sm text-muted-foreground">
          <Mono>{job.job_id}</Mono>
          <JobStatusBadge status={job.status} />
          <span>{elapsed}s (desde que abriste la vista)</span>
        </div>
      </header>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Pipeline Scrum (progreso global)</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="h-1.5 w-full overflow-hidden rounded bg-muted">
            <div className="h-full w-1/3 animate-pulse rounded bg-blue-500" />
          </div>
          <ol className="grid grid-cols-2 gap-x-6 gap-y-1 sm:grid-cols-3">
            {PHASES.map((phase) => (
              <li
                key={phase}
                className="flex items-center gap-2 text-xs text-muted-foreground"
              >
                <span className="inline-block h-1.5 w-1.5 rounded-full bg-muted-foreground/40" />
                <Mono>{phase}</Mono>
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
