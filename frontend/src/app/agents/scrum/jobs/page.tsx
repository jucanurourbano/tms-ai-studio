"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { JobStatusBadge, Mono } from "@/components/ef/badges";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ApiError } from "@/lib/api/client";
import { scrumApi } from "@/lib/api/scrum";
import type { ScrumJobList } from "@/lib/types/scrum";

const PAGE_SIZE = 20;

export default function ScrumJobsHistoryPage() {
  const [data, setData] = useState<ScrumJobList | null>(null);
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchList = useCallback(() => {
    scrumApi
      .listJobs(PAGE_SIZE, offset)
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((err) =>
        setError(
          err instanceof ApiError ? err.message : "No se pudo cargar el historial.",
        ),
      )
      .finally(() => setLoading(false));
  }, [offset]);

  useEffect(() => {
    fetchList();
  }, [fetchList]);

  function goTo(newOffset: number) {
    setLoading(true);
    setOffset(newOffset);
  }

  const total = data?.total ?? 0;
  const items = data?.items ?? [];
  const from = total === 0 ? 0 : offset + 1;
  const to = Math.min(offset + PAGE_SIZE, total);

  return (
    <div className="p-6 max-w-4xl">
      <header className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-heading font-semibold">Historial</h1>
          <p className="text-sm text-muted-foreground">
            Planes generados por el Agente Scrum.
          </p>
        </div>
        <Link href="/agents/scrum/new" className={buttonVariants({ size: "sm" })}>
          Nuevo plan
        </Link>
      </header>

      {error && (
        <div className="mb-4 rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="overflow-hidden rounded-md border">
        <Table>
          <TableHeader className="bg-muted/60">
            <TableRow className="hover:bg-transparent">
              <TableHead>Plan</TableHead>
              <TableHead>Estado</TableHead>
              <TableHead>EF de origen / Padre</TableHead>
              <TableHead className="text-right">Acción</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody className="[&_tr:nth-child(even)]:bg-muted/25">
            {loading ? (
              <TableRow>
                <TableCell colSpan={4} className="text-sm text-muted-foreground">
                  Cargando…
                </TableCell>
              </TableRow>
            ) : items.length === 0 ? (
              <TableRow>
                <TableCell colSpan={4} className="text-sm text-muted-foreground">
                  No hay planes todavía.
                </TableCell>
              </TableRow>
            ) : (
              items.map((job) => (
                <TableRow key={job.job_id}>
                  <TableCell>
                    <Mono>{job.job_id}</Mono>
                  </TableCell>
                  <TableCell>
                    <JobStatusBadge status={job.status} />
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {job.parent_job_id ? (
                      <span>
                        afinamiento de <Mono>{job.parent_job_id}</Mono>
                      </span>
                    ) : job.input_job_id ? (
                      <span>
                        EF <Mono>{job.input_job_id}</Mono>
                      </span>
                    ) : (
                      "—"
                    )}
                  </TableCell>
                  <TableCell className="text-right">
                    <Link
                      href={`/agents/scrum/jobs/${job.job_id}`}
                      className="text-sm underline underline-offset-4"
                    >
                      Abrir
                    </Link>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      <div className="mt-3 flex items-center justify-between text-xs text-muted-foreground">
        <span>
          {from}–{to} de {total}
        </span>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={offset === 0 || loading}
            onClick={() => goTo(Math.max(0, offset - PAGE_SIZE))}
          >
            Anterior
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={to >= total || loading}
            onClick={() => goTo(offset + PAGE_SIZE)}
          >
            Siguiente
          </Button>
        </div>
      </div>
    </div>
  );
}
