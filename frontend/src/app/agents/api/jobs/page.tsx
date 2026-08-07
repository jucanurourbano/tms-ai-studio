"use client";

import { Plus } from "lucide-react";
import Link from "next/link";
import { Suspense } from "react";

import { JobsHistoryView } from "@/components/history/jobs-history-view";
import { PageContainer } from "@/components/shell/page-container";
import { PageHeader } from "@/components/shell/page-header";
import { buttonVariants } from "@/components/ui/button";
import { apisApi } from "@/lib/api/apis";

/**
 * Historial del Agente API. Toda la mecánica (pestañas por estado con
 * contadores, paginación de servidor, numeración, búsqueda y afordancia de clic)
 * vive en `JobsHistoryView`, compartido con los demás agentes.
 */
export default function ApiJobsHistoryPage() {
  return (
    <PageContainer className="animate-rise">
      <PageHeader
        module="api"
        icon="plug"
        eyebrow="Construir"
        title="Historial"
        description="Contratos de API generados por el Agente API."
        action={
          <Link
            href="/agents/api/new"
            className={buttonVariants({ size: "sm", className: "gap-1.5" })}
          >
            <Plus className="h-3.5 w-3.5" />
            Nueva especificación
          </Link>
        }
      />

      <Suspense
        fallback={<div className="h-64 animate-pulse rounded-xl bg-muted/40" />}
      >
        <JobsHistoryView
          basePath="/agents/api/jobs"
          fetchJobs={(limit, offset, estado) =>
            apisApi.listJobs(limit, offset, estado)
          }
          emptyLabel="No hay contratos de API todavía."
          searchHint="El título se hereda del EF de origen. El buscador filtra por título dentro de la página actual."
        />
      </Suspense>
    </PageContainer>
  );
}
