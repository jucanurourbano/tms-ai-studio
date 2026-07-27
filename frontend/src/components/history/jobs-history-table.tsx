"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { JobStatusBadge, Mono } from "@/components/ef/badges";
import { DataTable, type DataColumn } from "@/components/ui/data-table";
import { SearchInput } from "@/components/ui/search-input";
import { Badge } from "@/components/ui/badge";
import {
  absoluteTime,
  filterByTitle,
  relativeTime,
  sourceLabel,
} from "@/lib/format";
import type { JobStatus, SourceType } from "@/lib/types/ef";

/** Fila del historial (subconjunto común a EF, Scrum y Arquitectura). */
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
    return <span className="text-xs text-meta-foreground">—</span>;
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
function VersionCell({ row, basePath }: { row: HistoryRow; basePath: string }) {
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
 * Historial de jobs, compartido por EF, Scrum y Arquitectura.
 *
 * Usa `DataTable`, así que en escritorio es tabla y en móvil una card por job
 * (título = nombre del análisis, id como meta, badges de fuente/estado/versión y
 * la fecha como par). El buscador va integrado en la cabecera del card.
 */
export function JobsHistoryTable({
  rows,
  basePath,
  loading,
  emptyLabel,
  footer,
}: {
  rows: HistoryRow[];
  basePath: string;
  loading: boolean;
  emptyLabel: string;
  footer?: React.ReactNode;
}) {
  const [query, setQuery] = useState("");
  const filtered = useMemo(() => filterByTitle(rows, query), [rows, query]);

  const columns: DataColumn<HistoryRow>[] = [
    {
      key: "title",
      label: "Título",
      cardRole: "title",
      render: (row) => (
        <Link
          href={`${basePath}/${row.job_id}`}
          className="font-medium underline-offset-4 hover:text-primary hover:underline"
        >
          {row.title?.trim() || "(sin título)"}
        </Link>
      ),
    },
    {
      key: "job_id",
      label: "Id",
      cardRole: "meta",
      render: (row) => <Mono className="text-meta-foreground">{row.job_id}</Mono>,
    },
    {
      key: "source",
      label: "Fuente",
      width: "w-28",
      cardRole: "badge",
      render: (row) => <SourceBadge source={row.source_type} />,
    },
    {
      key: "status",
      label: "Estado",
      width: "w-40",
      cardRole: "badge",
      render: (row) => <JobStatusBadge status={row.status} />,
    },
    {
      key: "version",
      label: "Versión",
      width: "w-28",
      cardRole: "badge",
      render: (row) => <VersionCell row={row} basePath={basePath} />,
    },
    {
      key: "created_at",
      label: "Fecha",
      numeric: true,
      width: "w-32",
      nowrap: true,
      render: (row) => (
        <span
          className="text-xs text-meta-foreground"
          title={absoluteTime(row.created_at)}
        >
          {relativeTime(row.created_at)}
        </span>
      ),
    },
  ];

  return (
    <DataTable
      columns={columns}
      rows={filtered}
      rowKey={(row) => row.job_id}
      loading={loading}
      zebra
      footer={footer}
      empty={
        query ? "Sin resultados para la búsqueda." : emptyLabel
      }
      toolbar={
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <SearchInput
            value={query}
            onChange={setQuery}
            placeholder="Buscar por título…"
            aria-label="Buscar por título"
            className="sm:max-w-xs"
          />
          <span className="text-xs text-meta-foreground sm:ml-auto">
            {filtered.length === rows.length
              ? `${rows.length} en esta página`
              : `${filtered.length} de ${rows.length} en esta página`}
          </span>
        </div>
      }
    />
  );
}
