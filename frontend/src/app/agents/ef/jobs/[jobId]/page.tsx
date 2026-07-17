"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { Mono } from "@/components/ef/badges";
import { ProgressView } from "@/components/ef/progress-view";
import { ResultView } from "@/components/ef/result-view";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api/client";
import { efApi } from "@/lib/api/ef";
import type { JobDetail } from "@/lib/types/ef";

export default function JobPage() {
  const params = useParams<{ jobId: string }>();
  const jobId = params.jobId;

  const [job, setJob] = useState<JobDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // setState solo en callbacks async (no síncrono dentro del efecto).
  const fetchJob = useCallback(() => {
    efApi
      .getJob(jobId)
      .then((j) => {
        setJob(j);
        setError(null);
      })
      .catch((err) =>
        setError(
          err instanceof ApiError ? err.message : "No se pudo cargar el job.",
        ),
      )
      .finally(() => setLoading(false));
  }, [jobId]);

  useEffect(() => {
    fetchJob();
  }, [fetchJob]);

  function retry() {
    setLoading(true);
    setError(null);
    fetchJob();
  }

  if (loading) {
    return (
      <div className="p-6 max-w-3xl space-y-3">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  if (error || !job) {
    return (
      <div className="p-6 max-w-3xl">
        <Card>
          <CardHeader>
            <CardTitle className="text-base text-red-600">
              No se pudo cargar el análisis
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <p className="text-muted-foreground">{error}</p>
            <Mono>{jobId}</Mono>
            <div>
              <Button variant="outline" size="sm" onClick={retry}>
                Reintentar
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (job.status === "FAILED") {
    return (
      <div className="p-6 max-w-3xl">
        <Card>
          <CardHeader>
            <CardTitle className="text-base text-red-600">
              El análisis falló
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <Mono>{job.job_id}</Mono>
            <pre className="whitespace-pre-wrap rounded bg-muted p-3 font-mono text-xs text-red-700">
              {job.error ?? "Sin detalle del error."}
            </pre>
            <Link
              href="/agents/ef/new"
              className="text-sm underline underline-offset-4"
            >
              Iniciar un nuevo análisis
            </Link>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (job.status === "COMPLETED" || job.status === "COMPLETED_WITH_WARNINGS") {
    return <ResultView job={job} />;
  }

  // PENDING / RUNNING / NEEDS_INPUT
  return <ProgressView job={job} onUpdate={setJob} />;
}
