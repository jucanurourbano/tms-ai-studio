"use client";

import { Plus } from "lucide-react";
import Link from "next/link";
import { Suspense } from "react";

import { JobsHistoryView } from "@/components/history/jobs-history-view";
import { PageContainer } from "@/components/shell/page-container";
import { PageHeader } from "@/components/shell/page-header";
import { buttonVariants } from "@/components/ui/button";
import { qaApi } from "@/lib/api/qa";

/**
 * Historial del Agente QA. Toda la mecánica (pestañas por estado con
 * contadores, paginación de servidor, numeración, búsqueda y afordancia de clic)
 * vive en `JobsHistoryView`, compartido con los demás agentes.
 */
export default function QaJobsHistoryPage() {
  return (
    <PageContainer className="animate-rise">
      <PageHeader
        module="qa"
        icon="shield-check"
        eyebrow="Verificar"
        title="Historial"
        description="Planes de pruebas generados por el Agente QA."
        action={
          <Link
            href="/agents/qa/new"
            className={buttonVariants({ size: "sm", className: "gap-1.5" })}
          >
            <Plus className="h-3.5 w-3.5" />
            Nuevo plan de pruebas
          </Link>
        }
      />

      <Suspense
        fallback={<div className="h-64 animate-pulse rounded-xl bg-muted/40" />}
      >
        <JobsHistoryView
          basePath="/agents/qa/jobs"
          fetchJobs={(limit, offset, estado) =>
            qaApi.listJobs(limit, offset, estado)
          }
          emptyLabel="No hay planes de pruebas todavía."
          searchHint="El título se hereda del EF de origen. El buscador filtra por título dentro de la página actual."
        />
      </Suspense>
    </PageContainer>
  );
}
