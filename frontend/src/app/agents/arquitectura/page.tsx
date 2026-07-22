import { History, Layers } from "lucide-react";

import { ActionCard } from "@/components/shell/action-card";
import { PageHeader } from "@/components/shell/page-header";

export default function ArquitecturaLandingPage() {
  return (
    <div className="mx-auto max-w-5xl p-6">
      <PageHeader
        variant="hero"
        icon="layers"
        eyebrow="Diseñar"
        title="Agente Arquitectura"
        description="Convierte un plan Scrum listo en el diseño técnico de la solución: estilo arquitectónico justificado, componentes, stack recomendado, ADRs, integraciones, contratos, requisitos transversales y diagramas — con trazabilidad total al EF y al Scrum."
      />

      <div className="grid gap-4 sm:grid-cols-2">
        <ActionCard
          href="/agents/arquitectura/new"
          icon={<Layers />}
          title="Nuevo diseño"
          description="Elige un plan Scrum listo y genera la arquitectura."
          footer={
            <>
              Requiere un Scrum con <b>ready_for_next_stage</b> en verde.
            </>
          }
        />
        <ActionCard
          href="/agents/arquitectura/jobs"
          icon={<History />}
          title="Historial"
          description="Diseños generados y su estado."
          footer="Abre un diseño para revisarlo y afinarlo con el Arquitecto."
        />
      </div>
    </div>
  );
}
