"use client";

import { AlertTriangle, Eye } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { JobStatusBadge } from "@/components/ef/badges";
import { JobIdChip } from "@/components/history/job-id-chip";
import { JobStatusTabs } from "@/components/history/status-tabs";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { DataTable, type DataColumn } from "@/components/ui/data-table";
import { SearchInput } from "@/components/ui/search-input";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { ApiError } from "@/lib/api/client";
import { absoluteTime, filterByTitle, relativeTime, sourceLabel } from "@/lib/format";
import type {
  JobList,
  JobStatusCounts,
  JobStatusGroup,
  SourceType,
} from "@/lib/types/ef";

const PAGE_SIZE = 20;

/** Grupo por defecto: lo primero que se ve es lo que se puede usar. */
const GRUPO_DEFECTO: JobStatusGroup = "completados";

const GRUPOS_VALIDOS: JobStatusGroup[] = [
  "completados",
  "avisos",
  "en_proceso",
  "fallidos",
  "todos",
];

/** Fila del historial (subconjunto común a EF, Scrum y Arquitectura). */
export interface HistoryRow {
  job_id: string;
  title?: string | null;
  source_type?: SourceType | null;
  status: string;
  version?: number | null;
  parent_job_id?: string | null;
  created_at?: string | null;
}

function SourceBadge({ source }: { source?: SourceType | null }) {
  if (!source) return <span className="text-xs text-meta-foreground">—</span>;
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

/**
 * Historial de jobs **reutilizable** por cualquier agente del ISDF (hoy EF, Scrum
 * y Arquitectura; mañana BD, API…). Recibe cómo pedir los datos y a dónde
 * enlazar; todo lo demás — pestañas, contadores, paginación, búsqueda,
 * numeración y afordancia de clic — es el mismo patrón para todos.
 *
 * Decisiones que conviene no perder:
 *
 * - **Abre en "Completados"**: al entrar, lo primero que se ve es lo que se puede
 *   usar. Los estados intermedios y los fallos están a un clic, no a la vista.
 *   El default de la API sigue siendo `todos`; esto es una decisión de producto.
 * - **La pestaña vive en la URL** (`?estado=fallidos`), así que un historial
 *   filtrado se puede compartir o recuperar con el botón atrás.
 * - **El filtro y la paginación son de servidor**: `total` es el de la pestaña.
 *   La búsqueda por título sí es local (filtra la página cargada) y se anuncia
 *   como tal.
 */
export function JobsHistoryView({
  basePath,
  fetchJobs,
  emptyLabel,
  searchHint = "El buscador filtra por título dentro de la página actual.",
}: {
  /** Ruta base del detalle: `${basePath}/${job_id}`. */
  basePath: string;
  fetchJobs: (
    limit: number,
    offset: number,
    estado: JobStatusGroup,
  ) => Promise<JobList>;
  emptyLabel: string;
  searchHint?: string;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const estadoUrl = searchParams.get("estado") as JobStatusGroup | null;
  const estado: JobStatusGroup =
    estadoUrl && GRUPOS_VALIDOS.includes(estadoUrl) ? estadoUrl : GRUPO_DEFECTO;

  const [data, setData] = useState<JobList | null>(null);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  // Los contadores se conservan entre cargas para que los tabs no parpadeen al
  // cambiar de pestaña (el número no cambia por filtrar).
  const [counts, setCounts] = useState<JobStatusCounts | undefined>();

  const cargar = useCallback(() => {
    fetchJobs(PAGE_SIZE, offset, estado)
      .then((d) => {
        setData(d);
        if (d.status_counts) setCounts(d.status_counts);
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
  }, [fetchJobs, offset, estado]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  function cambiarEstado(grupo: JobStatusGroup) {
    if (grupo === estado) return;
    setLoading(true);
    setOffset(0); // otra pestaña, otra paginación
    setQuery("");
    const params = new URLSearchParams(searchParams.toString());
    params.set("estado", grupo);
    router.replace(`${pathname}?${params.toString()}`, { scroll: false });
  }

  function irA(nuevoOffset: number) {
    setLoading(true);
    setOffset(nuevoOffset);
  }

  const total = data?.total ?? 0;
  const items = useMemo(
    () => filterByTitle((data?.items ?? []) as HistoryRow[], query),
    [data, query],
  );
  const desde = total === 0 ? 0 : offset + 1;
  const hasta = Math.min(offset + PAGE_SIZE, total);

  const columns: DataColumn<HistoryRow>[] = [
    {
      key: "n",
      label: "#",
      width: "w-12",
      numeric: true,
      // En la card el número va discreto en la esquina, no como par.
      cardRole: "hidden",
      // Numeración CONTINUA a través de la paginación: en la página 2 la primera
      // fila es la 21, no la 1. Se calcula con el offset del servidor, así que
      // respeta la pestaña activa.
      render: (_row, index) => (
        <span className="text-[11px] text-meta-foreground">
          {offset + index + 1}
        </span>
      ),
    },
    {
      key: "title",
      label: "Título",
      cardRole: "title",
      render: (row, index) => (
        <div className="flex min-w-0 items-center gap-2">
          {/* En la card el número va discreto delante del título (la columna # se
              oculta en móvil). */}
          <span className="shrink-0 text-[11px] text-meta-foreground md:hidden">
            #{offset + index + 1}
          </span>
          <Link
            href={`${basePath}/${row.job_id}`}
            // El enlace real permite abrir en pestaña nueva y navegar con teclado,
            // aunque toda la fila sea clicable.
            onClick={(e) => e.stopPropagation()}
            className="min-w-0 truncate font-medium text-foreground underline-offset-4 transition-colors hover:text-primary hover:underline"
          >
            {row.title?.trim() || "(sin título)"}
          </Link>
        </div>
      ),
    },
    {
      key: "job_id",
      label: "Id",
      width: "w-32",
      cardRole: "meta",
      render: (row) => <JobIdChip id={row.job_id} />,
    },
    {
      key: "source",
      label: "Fuente",
      width: "w-24",
      cardRole: "badge",
      render: (row) => <SourceBadge source={row.source_type} />,
    },
    {
      key: "status",
      label: "Estado",
      width: "w-44",
      cardRole: "badge",
      render: (row) => (
        <JobStatusBadge status={row.status as never} />
      ),
    },
    {
      key: "version",
      label: "Versión",
      width: "w-24",
      cardRole: "badge",
      render: (row) => {
        const version = row.version ?? 1;
        const refinado = version > 1 && !!row.parent_job_id;
        return refinado ? (
          <Link
            href={`${basePath}/${row.parent_job_id}`}
            onClick={(e) => e.stopPropagation()}
            title={`Afinamiento — ver job padre (v${version - 1})`}
          >
            <Badge
              variant="outline"
              className="border-violet-300 bg-violet-50 font-mono text-violet-700 hover:underline"
            >
              v{version} · padre
            </Badge>
          </Link>
        ) : (
          <Badge variant="outline" className="font-mono text-muted-foreground">
            v{version}
          </Badge>
        );
      },
    },
    {
      key: "created_at",
      label: "Fecha",
      width: "w-28",
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
    {
      key: "ver",
      label: "Ver",
      width: "w-16",
      numeric: true,
      cardRole: "actions",
      render: (row) => <VerButton row={row} basePath={basePath} />,
    },
  ];

  return (
    <div className="space-y-3">
      <JobStatusTabs
        value={estado}
        counts={counts}
        onChange={cambiarEstado}
        disabled={loading && !data}
      />

      {error && (
        <div className="rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      <DataTable
        columns={columns}
        rows={items}
        rowKey={(row) => row.job_id}
        loading={loading}
        zebra
        onRowClick={(row) => router.push(`${basePath}/${row.job_id}`)}
        empty={
          query
            ? "Sin resultados para la búsqueda en esta página."
            : emptyLabel
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
              {total === 0
                ? "Sin resultados"
                : `${desde}–${hasta} de ${total}`}
            </span>
          </div>
        }
        footer={
          <div className="flex items-center justify-between gap-2 text-xs text-meta-foreground">
            <span>{searchHint}</span>
            <div className="flex shrink-0 gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={offset === 0 || loading}
                onClick={() => irA(Math.max(0, offset - PAGE_SIZE))}
              >
                Anterior
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={hasta >= total || loading}
                onClick={() => irA(offset + PAGE_SIZE)}
              >
                Siguiente
              </Button>
            </div>
          </div>
        }
      />
    </div>
  );
}

/**
 * Acción explícita de la fila. En un job **fallido** no hay artefacto que ver, así
 * que cambia de icono y de texto: lo que se abre es el detalle del error. Decirlo
 * antes del clic evita la decepción de abrir y encontrar una pantalla de fallo.
 *
 * Es un `<Link>` con estilo de botón, no un `<Button>`: el `Button` de Base UI
 * espera un `<button>` nativo y avisa por consola si se le mete un ancla dentro.
 * Además, siendo enlace real funcionan el clic con rueda y "abrir en pestaña
 * nueva". `stopPropagation` evita que además dispare el clic de la fila.
 */
function VerButton({ row, basePath }: { row: HistoryRow; basePath: string }) {
  const fallido = row.status === "FAILED";
  const etiqueta = fallido ? "Ver detalle del error" : "Ver artefacto";
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <Link
            href={`${basePath}/${row.job_id}`}
            aria-label={etiqueta}
            onClick={(e) => e.stopPropagation()}
            className={buttonVariants({
              variant: "ghost",
              size: "icon-sm",
              className: "text-meta-foreground hover:text-primary",
            })}
          >
            {fallido ? (
              <AlertTriangle className="text-destructive" />
            ) : (
              <Eye />
            )}
          </Link>
        }
      />
      <TooltipContent>{etiqueta}</TooltipContent>
    </Tooltip>
  );
}
