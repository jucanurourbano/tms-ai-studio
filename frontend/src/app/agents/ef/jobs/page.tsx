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
import { efApi } from "@/lib/api/ef";
import type { JobList } from "@/lib/types/ef";

const PAGE_SIZE = 20;

export default function JobsHistoryPage() {
  const [data, setData] = useState<JobList | null>(null);
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // setState solo en callbacks async (no síncrono dentro del efecto).
  const fetchList = useCallback(() => {
    efApi
      .listJobs(PAGE_SIZE, offset)
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((err) =>
        setError(
          err instanceof ApiError
            ? err.message
            : "No se pudo cargar el historial.",
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
            Análisis realizados por el Agente EF.
          </p>
        </div>
        <Link href="/agents/ef/new" className={buttonVariants({ size: "sm" })}>
          Nuevo análisis
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
              <TableHead>Job</TableHead>
              <TableHead>Estado</TableHead>
              <TableHead>Versión / Padre</TableHead>
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
                  No hay análisis todavía.
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
                    ) : (
                      "original"
                    )}
                  </TableCell>
                  <TableCell className="text-right">
                    <Link
                      href={`/agents/ef/jobs/${job.job_id}`}
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

      <p className="mt-3 text-xs text-muted-foreground">
        Nota: el endpoint de listado expone id, estado y job padre. El título y
        la fecha se muestran al abrir cada análisis.
      </p>
    </div>
  );
}
