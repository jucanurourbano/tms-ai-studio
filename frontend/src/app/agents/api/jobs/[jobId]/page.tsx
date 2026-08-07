"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { ApiProgressView } from "@/components/api/progress-view";
import { ApiResultView } from "@/components/api/api-result-view";
import { Mono } from "@/components/ef/badges";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { apisApi } from "@/lib/api/apis";
import { ApiError } from "@/lib/api/client";
import type { ApiJobDetail } from "@/lib/types/api";

export default function ApiJobPage() {
  const params = useParams<{ jobId: string }>();
  const jobId = params.jobId;

  const [job, setJob] = useState<ApiJobDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchJob = useCallback(() => {
    apisApi
      .getJob(jobId)
      .then((j) => {
        setJob(j);
        setError(null);
      })
      .catch((err) =>
        setError(
          err instanceof ApiError
            ? err.message
            : "No se pudo cargar la especificación.",
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
              No se pudo cargar la especificación
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
              La especificación de API falló
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <Mono>{job.job_id}</Mono>
            <pre className="whitespace-pre-wrap rounded bg-muted p-3 font-mono text-xs text-red-700">
              {job.error ?? "Sin detalle del error."}
            </pre>
            <Link
              href="/agents/api/new"
              className="text-sm underline underline-offset-4"
            >
              Iniciar una nueva especificación
            </Link>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (job.status === "COMPLETED" || job.status === "COMPLETED_WITH_WARNINGS") {
    return <ApiResultView job={job} />;
  }

  return <ApiProgressView job={job} onUpdate={setJob} />;
}
