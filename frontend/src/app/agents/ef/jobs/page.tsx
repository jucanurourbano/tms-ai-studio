"use client";

import { Plus } from "lucide-react";
import Link from "next/link";
import { Suspense } from "react";

import { JobsHistoryView } from "@/components/history/jobs-history-view";
import { PageContainer } from "@/components/shell/page-container";
import { PageHeader } from "@/components/shell/page-header";
import { buttonVariants } from "@/components/ui/button";
import { efApi } from "@/lib/api/ef";

/**
 * Historial del Agente ef. Toda la mecánica (pestañas por estado con
 * contadores, paginación de servidor, numeración, búsqueda y afordancia de clic)
 * vive en `JobsHistoryView`, compartido con los demás agentes.
 *
 * El `Suspense` es obligatorio: `JobsHistoryView` lee la pestaña activa de la URL
 * con `useSearchParams`, y sin límite de suspensión Next no puede prerenderizar
 * esta página.
 */
export default function JobsHistoryPage() {
  return (
    <PageContainer className="animate-rise">
      <PageHeader
        module="ef"
        icon="file-search"
        eyebrow="Especificar"
        title="Historial"
        description="Análisis realizados por el Agente EF."
        action={
          <Link
            href="/agents/ef/new"
            className={buttonVariants({ size: "sm", className: "gap-1.5" })}
          >
            <Plus className="h-3.5 w-3.5" />
            Nuevo análisis
          </Link>
        }
      />

      <Suspense
        fallback={
          <div className="h-64 animate-pulse rounded-xl bg-muted/40" />
        }
      >
        <JobsHistoryView
          basePath="/agents/ef/jobs"
          fetchJobs={(limit, offset, estado) =>
            efApi.listJobs(limit, offset, estado)
          }
          emptyLabel="No hay análisis todavía."
          searchHint="El buscador filtra por título dentro de la página actual."
        />
      </Suspense>
    </PageContainer>
  );
}
