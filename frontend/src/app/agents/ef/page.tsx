import Link from "next/link";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export default function EFLandingPage() {
  return (
    <div className="p-6 max-w-4xl">
      <div className="mb-6 overflow-hidden rounded-xl brand-gradient px-6 py-7 text-white shadow-sm">
        <div className="text-[11px] font-semibold uppercase tracking-widest text-white/80">
          Especificar
        </div>
        <h1 className="text-2xl font-heading font-semibold tracking-tight">
          Agente EF
        </h1>
        <p className="mt-1 text-sm text-white/85 max-w-2xl">
          Traduce un documento de Procesos (o texto libre) al lenguaje de
          Sistemas: interpretación, requisitos, modelo de datos y preguntas de
          afinamiento, con trazabilidad a la evidencia de origen.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <Link href="/agents/ef/new">
          <Card className="h-full hover:bg-accent transition-colors">
            <CardHeader>
              <CardTitle className="text-base">Nuevo análisis</CardTitle>
              <CardDescription>
                Analiza un .docx/.pdf o pega texto libre.
              </CardDescription>
            </CardHeader>
            <CardContent className="text-sm text-muted-foreground">
              Genera una Especificación Funcional (EF) v1.2.0.
            </CardContent>
          </Card>
        </Link>

        <Link href="/agents/ef/jobs">
          <Card className="h-full hover:bg-accent transition-colors">
            <CardHeader>
              <CardTitle className="text-base">Historial</CardTitle>
              <CardDescription>
                Revisa análisis anteriores y su estado.
              </CardDescription>
            </CardHeader>
            <CardContent className="text-sm text-muted-foreground">
              Abre un análisis para ver su artefacto y afinarlo.
            </CardContent>
          </Card>
        </Link>
      </div>
    </div>
  );
}
