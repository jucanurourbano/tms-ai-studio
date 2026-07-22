"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { Mono } from "@/components/ef/badges";
import { ArchitectureProgressView } from "@/components/arquitectura/progress-view";
import { ArchitectureResultView } from "@/components/arquitectura/architecture-result-view";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { arquitecturaApi } from "@/lib/api/arquitectura";
import { ApiError } from "@/lib/api/client";
import type { ArchJobDetail } from "@/lib/types/arquitectura";

export default function ArquitecturaJobPage() {
  const params = useParams<{ jobId: string }>();
  const jobId = params.jobId;

  const [job, setJob] = useState<ArchJobDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchJob = useCallback(() => {
    arquitecturaApi
      .getJob(jobId)
      .then((j) => {
        setJob(j);
        setError(null);
      })
      .catch((err) =>
        setError(
          err instanceof ApiError ? err.message : "No se pudo cargar el diseño.",
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
              No se pudo cargar el diseño
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
              El diseño falló
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <Mono>{job.job_id}</Mono>
            <pre className="whitespace-pre-wrap rounded bg-muted p-3 font-mono text-xs text-red-700">
              {job.error ?? "Sin detalle del error."}
            </pre>
            <Link
              href="/agents/arquitectura/new"
              className="text-sm underline underline-offset-4"
            >
              Iniciar un nuevo diseño
            </Link>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (job.status === "COMPLETED" || job.status === "COMPLETED_WITH_WARNINGS") {
    return <ArchitectureResultView job={job} />;
  }

  return <ArchitectureProgressView job={job} onUpdate={setJob} />;
}
