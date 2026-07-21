"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { JobStatusBadge, Mono } from "@/components/ef/badges";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  absoluteTime,
  filterByTitle,
  relativeTime,
  sourceLabel,
} from "@/lib/format";
import type { JobStatus, SourceType } from "@/lib/types/ef";

/** Fila del historial (subconjunto común a EF y Scrum). */
export interface HistoryRow {
  job_id: string;
  title?: string | null;
  source_type?: SourceType | null;
  status: JobStatus;
  version?: number | null;
  parent_job_id?: string | null;
  created_at?: string | null;
}

function SourceBadge({ source }: { source?: SourceType | null }) {
  if (!source) {
    return <span className="text-xs text-muted-foreground">—</span>;
  }
  const cls =
    source === "document"
      ? "border-sky-300 bg-sky-50 text-sky-700"
      : "border-slate-300 bg-slate-50 text-slate-700";
  return (
    <Badge variant="outline" className={cls}>
      {sourceLabel(source)}
    </Badge>
  );
}

/** Versión del job. Para v2+ (refinada) es un enlace al job padre. */
function VersionCell({
  row,
  basePath,
}: {
  row: HistoryRow;
  basePath: string;
}) {
  const version = row.version ?? 1;
  const refined = version > 1 && !!row.parent_job_id;

  if (refined) {
    return (
      <Link
        href={`${basePath}/${row.parent_job_id}`}
        title={`Afinamiento — ver job padre (v${version - 1})`}
      >
        <Badge
          variant="outline"
          className="border-violet-300 bg-violet-50 font-mono text-violet-700 hover:underline"
        >
          v{version} · padre
        </Badge>
      </Link>
    );
  }
  return (
    <Badge variant="outline" className="font-mono text-muted-foreground">
      v{version}
    </Badge>
  );
}

/**
 * Tabla de historial reutilizable (EF y Scrum): columnas Título/Fuente/Estado/
 * Versión/Fecha, con buscador client-side por título sobre la página actual (v1).
 * El orden (más reciente primero) lo garantiza el backend.
 */
export function JobsHistoryTable({
  rows,
  basePath,
  loading,
  emptyLabel,
}: {
  rows: HistoryRow[];
  basePath: string;
  loading: boolean;
  emptyLabel: string;
}) {
  const [query, setQuery] = useState("");
  const filtered = useMemo(() => filterByTitle(rows, query), [rows, query]);

  return (
    <div>
      <div className="mb-3">
        <Input
          type="search"
          placeholder="Buscar por título…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="max-w-xs"
          aria-label="Buscar por título"
        />
      </div>

      <div className="overflow-x-auto rounded-md border">
        <Table className="min-w-[42rem]">
          <TableHeader className="bg-muted/60">
            <TableRow className="hover:bg-transparent">
              <TableHead>Título</TableHead>
              <TableHead>Fuente</TableHead>
              <TableHead>Estado</TableHead>
              <TableHead>Versión</TableHead>
              <TableHead className="text-right">Fecha</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody className="[&_tr:nth-child(even)]:bg-muted/25">
            {loading ? (
              <TableRow>
                <TableCell colSpan={5} className="text-sm text-muted-foreground">
                  Cargando…
                </TableCell>
              </TableRow>
            ) : filtered.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="text-sm text-muted-foreground">
                  {query ? "Sin resultados para la búsqueda." : emptyLabel}
                </TableCell>
              </TableRow>
            ) : (
              filtered.map((row) => (
                <TableRow key={row.job_id}>
                  <TableCell>
                    <Link
                      href={`${basePath}/${row.job_id}`}
                      className="font-medium underline-offset-4 hover:underline"
                    >
                      {row.title?.trim() || "(sin título)"}
                    </Link>
                    <div>
                      <Mono className="text-muted-foreground">
                        {row.job_id}
                      </Mono>
                    </div>
                  </TableCell>
                  <TableCell>
                    <SourceBadge source={row.source_type} />
                  </TableCell>
                  <TableCell>
                    <JobStatusBadge status={row.status} />
                  </TableCell>
                  <TableCell>
                    <VersionCell row={row} basePath={basePath} />
                  </TableCell>
                  <TableCell
                    className="whitespace-nowrap text-right text-xs text-muted-foreground"
                    title={absoluteTime(row.created_at)}
                  >
                    {relativeTime(row.created_at)}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
