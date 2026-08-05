import { Database, History } from "lucide-react";

import { ActionCard } from "@/components/shell/action-card";
import { PageContainer } from "@/components/shell/page-container";
import { PageHeader } from "@/components/shell/page-header";

export default function BdLandingPage() {
  return (
    <PageContainer>
      <PageHeader
        variant="hero"
        icon="database"
        eyebrow="Diseñar"
        title="Agente Base de Datos"
        description="Convierte un diseño de arquitectura listo en el modelo de datos físico: tablas tipadas, claves, índices justificados, restricciones derivadas de las reglas del EF, DDL ejecutable, datos semilla, diccionario y diagrama entidad-relación."
      />

      <div className="grid gap-4 sm:grid-cols-2">
        <ActionCard
          href="/agents/bd/new"
          icon={<Database />}
          title="Nuevo modelo de datos"
          description="Elige un diseño de arquitectura listo y genera el esquema."
          footer={
            <>
              Requiere una arquitectura con <b>ready_for_next_stage</b> en verde.
            </>
          }
        />
        <ActionCard
          href="/agents/bd/jobs"
          icon={<History />}
          title="Historial"
          description="Modelos generados y su estado."
          footer="Abre un modelo para revisarlo y afinarlo con el DBA."
        />
      </div>
    </PageContainer>
  );
}
