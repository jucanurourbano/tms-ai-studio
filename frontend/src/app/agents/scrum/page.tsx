import Link from "next/link";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export default function ScrumLandingPage() {
  return (
    <div className="p-6 max-w-4xl">
      <div className="mb-6 overflow-hidden rounded-xl brand-gradient px-6 py-7 text-white shadow-sm">
        <div className="text-[11px] font-semibold uppercase tracking-widest text-white/80">
          Gestionar
        </div>
        <h1 className="text-2xl font-heading font-semibold tracking-tight">
          Agente Scrum
        </h1>
        <p className="mt-1 text-sm text-white/85 max-w-2xl">
          Convierte una Especificación Funcional (EF) lista en insumos de
          planificación ágil: épicas, historias de usuario, criterios de
          aceptación, estimaciones, backlog priorizado, plan de sprints y
          preguntas al Product Owner — con trazabilidad total al EF.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <Link href="/agents/scrum/new">
          <Card className="h-full hover:bg-accent transition-colors">
            <CardHeader>
              <CardTitle className="text-base">Nuevo plan ágil</CardTitle>
              <CardDescription>
                Elige un análisis EF listo y genera el plan.
              </CardDescription>
            </CardHeader>
            <CardContent className="text-sm text-muted-foreground">
              Requiere un EF con <b>ready_for_next_stage</b> en verde.
            </CardContent>
          </Card>
        </Link>

        <Link href="/agents/scrum/jobs">
          <Card className="h-full hover:bg-accent transition-colors">
            <CardHeader>
              <CardTitle className="text-base">Historial</CardTitle>
              <CardDescription>Planes generados y su estado.</CardDescription>
            </CardHeader>
            <CardContent className="text-sm text-muted-foreground">
              Abre un plan para revisarlo y afinarlo con el PO.
            </CardContent>
          </Card>
        </Link>
      </div>
    </div>
  );
}
