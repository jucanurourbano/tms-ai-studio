"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { QaProgressView } from "@/components/qa/progress-view";
import { QaResultView } from "@/components/qa/qa-result-view";
import { Mono } from "@/components/ef/badges";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { qaApi } from "@/lib/api/qa";
import { ApiError } from "@/lib/api/client";
import type { QaJobDetail } from "@/lib/types/qa";

export default function QaJobPage() {
  const params = useParams<{ jobId: string }>();
  const jobId = params.jobId;

  const [job, setJob] = useState<QaJobDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchJob = useCallback(() => {
    qaApi
      .getJob(jobId)
      .then((j) => {
        setJob(j);
        setError(null);
      })
      .catch((err) =>
        setError(
          err instanceof ApiError
            ? err.message
            : "No se pudo cargar el plan de pruebas.",
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
              No se pudo cargar el plan de pruebas
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
              El plan de pruebas falló
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <Mono>{job.job_id}</Mono>
            <pre className="whitespace-pre-wrap rounded bg-muted p-3 font-mono text-xs text-red-700">
              {job.error ?? "Sin detalle del error."}
            </pre>
            <Link
              href="/agents/qa/new"
              className="text-sm underline underline-offset-4"
            >
              Iniciar un nuevo plan de pruebas
            </Link>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (job.status === "COMPLETED" || job.status === "COMPLETED_WITH_WARNINGS") {
    return <QaResultView job={job} />;
  }

  return <QaProgressView job={job} onUpdate={setJob} />;
}
