import { History, Plug } from "lucide-react";

import { ActionCard } from "@/components/shell/action-card";
import { PageContainer } from "@/components/shell/page-container";
import { PageHeader } from "@/components/shell/page-header";

export default function ApiLandingPage() {
  return (
    <PageContainer>
      <PageHeader
        variant="hero"
        icon="plug"
        eyebrow="Construir"
        title="Agente API"
        description="Convierte un modelo de datos listo en el contrato de las APIs: recursos y operaciones REST, esquemas de request y response tipados desde las columnas, matriz de autorización por actor, catálogo de errores, trazabilidad de reglas y el documento OpenAPI 3.1 descargable."
      />

      <div className="grid gap-4 sm:grid-cols-2">
        <ActionCard
          href="/agents/api/new"
          icon={<Plug />}
          title="Nueva especificación de API"
          description="Elige un modelo de datos listo y genera el contrato."
          footer={
            <>
              Requiere un modelo con <b>ready_for_next_stage</b> en verde.
            </>
          }
        />
        <ActionCard
          href="/agents/api/jobs"
          icon={<History />}
          title="Historial"
          description="Contratos generados y su estado."
          footer="Abre un contrato para revisarlo y afinarlo con el líder técnico."
        />
      </div>
    </PageContainer>
  );
}
