"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { JobsHistoryTable } from "@/components/history/jobs-history-table";
import { Button, buttonVariants } from "@/components/ui/button";
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
    <div className="p-6 max-w-full">
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

      <JobsHistoryTable
        rows={items}
        basePath="/agents/ef/jobs"
        loading={loading}
        emptyLabel="No hay análisis todavía."
      />

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
        El buscador filtra por título dentro de la página actual.
      </p>
    </div>
  );
}
