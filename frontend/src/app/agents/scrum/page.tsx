import { History, Kanban } from "lucide-react";

import { ActionCard } from "@/components/shell/action-card";
import { PageHeader } from "@/components/shell/page-header";

export default function ScrumLandingPage() {
  return (
    <div className="mx-auto max-w-5xl p-6">
      <PageHeader
        variant="hero"
        icon="kanban"
        eyebrow="Gestionar"
        title="Agente Scrum"
        description="Convierte una Especificación Funcional (EF) lista en insumos de planificación ágil: épicas, historias de usuario, criterios de aceptación, estimaciones, backlog priorizado, plan de sprints y preguntas al Product Owner — con trazabilidad total al EF."
      />

      <div className="grid gap-4 sm:grid-cols-2">
        <ActionCard
          href="/agents/scrum/new"
          icon={<Kanban />}
          title="Nuevo plan ágil"
          description="Elige un análisis EF listo y genera el plan."
          footer={
            <>
              Requiere un EF con <b>ready_for_next_stage</b> en verde.
            </>
          }
        />
        <ActionCard
          href="/agents/scrum/jobs"
          icon={<History />}
          title="Historial"
          description="Planes generados y su estado."
          footer="Abre un plan para revisarlo y afinarlo con el PO."
        />
      </div>
    </div>
  );
}
