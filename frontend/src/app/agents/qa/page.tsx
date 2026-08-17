import { History, ShieldCheck } from "lucide-react";

import { ActionCard } from "@/components/shell/action-card";
import { PageContainer } from "@/components/shell/page-container";
import { PageHeader } from "@/components/shell/page-header";

export default function QaLandingPage() {
  return (
    <PageContainer>
      <PageHeader
        variant="hero"
        icon="shield-check"
        eyebrow="Verificar"
        title="Agente QA"
        description="Convierte un plan ágil listo en el plan de pruebas: casos funcionales, negativos, de borde y de autorización derivados de los criterios de aceptación, matriz de trazabilidad requisito → historia → criterio → caso, datos de prueba, plan de ejecución con esfuerzo y exports a Excel."
      />

      <div className="grid gap-4 sm:grid-cols-2">
        <ActionCard
          href="/agents/qa/new"
          icon={<ShieldCheck />}
          title="Nuevo plan de pruebas"
          description="Elige un plan Scrum listo y diseña los casos."
          footer={
            <>
              Requiere un plan con <b>ready_for_next_stage</b> en verde.
            </>
          }
        />
        <ActionCard
          href="/agents/qa/jobs"
          icon={<History />}
          title="Historial"
          description="Planes de pruebas generados y su estado."
          footer="Abre un plan para revisarlo y afinarlo con el QA lead."
        />
      </div>
    </PageContainer>
  );
}
