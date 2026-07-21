import { FileSearch, History } from "lucide-react";

import { ActionCard } from "@/components/shell/action-card";
import { PageHeader } from "@/components/shell/page-header";

export default function EFLandingPage() {
  return (
    <div className="mx-auto max-w-5xl p-6">
      <PageHeader
        variant="hero"
        icon="file-search"
        eyebrow="Especificar"
        title="Agente EF"
        description="Traduce un documento de Procesos (o texto libre) al lenguaje de Sistemas: interpretación, requisitos, modelo de datos y preguntas de afinamiento, con trazabilidad a la evidencia de origen."
      />

      <div className="grid gap-4 sm:grid-cols-2">
        <ActionCard
          href="/agents/ef/new"
          icon={<FileSearch />}
          title="Nuevo análisis"
          description="Analiza un .docx/.pdf o pega texto libre."
          footer="Genera una Especificación Funcional (EF) v1.2.0."
        />
        <ActionCard
          href="/agents/ef/jobs"
          icon={<History />}
          title="Historial"
          description="Revisa análisis anteriores y su estado."
          footer="Abre un análisis para ver su artefacto y afinarlo."
        />
      </div>
    </div>
  );
}
