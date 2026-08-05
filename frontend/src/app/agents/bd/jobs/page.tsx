"use client";

import { Plus } from "lucide-react";
import Link from "next/link";
import { Suspense } from "react";

import { JobsHistoryView } from "@/components/history/jobs-history-view";
import { PageContainer } from "@/components/shell/page-container";
import { PageHeader } from "@/components/shell/page-header";
import { buttonVariants } from "@/components/ui/button";
import { bdApi } from "@/lib/api/bd";

/**
 * Historial del Agente BD. Toda la mecánica (pestañas por estado con
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
        module="bd"
        icon="database"
        eyebrow="Diseñar"
        title="Historial"
        description="Modelos de datos generados por el Agente BD."
        action={
          <Link
            href="/agents/bd/new"
            className={buttonVariants({ size: "sm", className: "gap-1.5" })}
          >
            <Plus className="h-3.5 w-3.5" />
            Nuevo modelo
          </Link>
        }
      />

      <Suspense
        fallback={
          <div className="h-64 animate-pulse rounded-xl bg-muted/40" />
        }
      >
        <JobsHistoryView
          basePath="/agents/bd/jobs"
          fetchJobs={(limit, offset, estado) =>
            bdApi.listJobs(limit, offset, estado)
          }
          emptyLabel="No hay modelos de datos todavía."
          searchHint="El título se hereda del EF de origen. El buscador filtra por título dentro de la página actual."
        />
      </Suspense>
    </PageContainer>
  );
}
