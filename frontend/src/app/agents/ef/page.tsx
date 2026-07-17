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
      <header className="mb-6">
        <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Especificar
        </div>
        <h1 className="text-xl font-heading font-semibold">Agente EF</h1>
        <p className="text-sm text-muted-foreground max-w-2xl">
          Traduce un documento de Procesos (o texto libre) al lenguaje de
          Sistemas: interpretación, requisitos, modelo de datos y preguntas de
          afinamiento, con trazabilidad a la evidencia de origen.
        </p>
      </header>

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
