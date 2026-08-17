"use client";

// NUEVO PLAN DE PRUEBAS.
//
// La pantalla tiene una pieza que ningún otro agente tiene: el **contrato de
// API**. No está en la cadena hacia atrás del plan Scrum sino hacia delante, así
// que no se descubre solo — se indica (QA-D1). Y por eso la lista solo aparece
// cuando ya hay un plan elegido: los contratos compatibles son los de ESA cadena,
// y ofrecer los de otra produciría casos de autorización perfectamente formados
// contra endpoints que este sistema no tiene.
//
// Sin contrato el plan se genera igual, sin casos de autorización y diciéndolo.
// Es una decisión legítima, no un error: la pantalla la ofrece como tal.

import { Loader2, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { PageContainer } from "@/components/shell/page-container";
import { PageHeader } from "@/components/shell/page-header";
import { SourceJobPicker } from "@/components/source/source-job-picker";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { qaApi } from "@/lib/api/qa";
import { ApiError } from "@/lib/api/client";
import type { AvailableScrumJob, CompatibleApiJob } from "@/lib/types/qa";

export default function NewTestPlanPage() {
  const router = useRouter();
  const [jobs, setJobs] = useState<AvailableScrumJob[] | null>(null);
  const [selected, setSelected] = useState<string>("");
  const [manual, setManual] = useState("");
  // Los contratos se guardan JUNTO AL plan para el que se pidieron: así, al
  // cambiar de plan, la lista anterior deja de aplicar por derivación en el
  // render, sin un efecto que la borre y provoque un renderizado en cascada.
  const [apiJobs, setApiJobs] = useState<{
    scrumJobId: string;
    items: CompatibleApiJob[];
  } | null>(null);
  const [apiJobId, setApiJobId] = useState("");
  const [maxCases, setMaxCases] = useState("");
  const [capacity, setCapacity] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    qaApi
      .availableScrumJobs()
      .then((d) => setJobs(d.items))
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "No se pudo cargar."),
      );
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const scrumJobId = (selected || manual).trim();

  // Los contratos compatibles dependen del plan elegido: se piden cuando hay uno.
  useEffect(() => {
    if (!scrumJobId) return;
    let vigente = true;
    qaApi
      .compatibleApiJobs(scrumJobId)
      .then((d) => {
        if (vigente) setApiJobs({ scrumJobId, items: d.items });
      })
      .catch(() => {
        if (vigente) setApiJobs({ scrumJobId, items: [] });
      });
    return () => {
      vigente = false;
    };
  }, [scrumJobId]);

  // Solo valen los contratos pedidos para ESTE plan. Mientras llega la respuesta
  // del nuevo, no se muestra la lista del anterior: elegir de esa lista sería
  // probar contra el contrato de otra cadena.
  const contratos =
    apiJobs && apiJobs.scrumJobId === scrumJobId ? apiJobs.items : null;

  /** Cambiar de plan invalida el contrato elegido: es de la cadena anterior. */
  function elegirPlan(id: string, origen: "lista" | "manual") {
    setSelected(origen === "lista" ? id : "");
    setManual(origen === "manual" ? id : "");
    setApiJobId("");
  }

  async function submit() {
    if (!scrumJobId) {
      toast.error("Elige un plan Scrum listo o pega su id.");
      return;
    }
    setSubmitting(true);
    try {
      const result = await qaApi.createPlan(scrumJobId, {
        apiJobId: apiJobId || null,
        maxCasesPerCriterion: maxCases ? Number(maxCases) : null,
        manualCapacityMinutes: capacity ? Number(capacity) : null,
      });
      toast.success("Plan de pruebas iniciado");
      router.push(`/agents/qa/jobs/${result.job_id}`);
    } catch (err) {
      toast.error("No se pudo generar el plan de pruebas", {
        description: err instanceof ApiError ? err.message : undefined,
      });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <PageContainer variant="form">
      <PageHeader
        module="qa"
        icon="shield-check"
        eyebrow="Verificar"
        title="Nuevo plan de pruebas"
        description={
          <>
            Elige un plan Scrum <b>listo</b> (semáforo en verde) como origen.
          </>
        }
      />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Plan Scrum</CardTitle>
          <CardDescription>
            Solo los planes listos habilitan el diseño de pruebas (gate de
            entrada). El EF de origen —de donde salen las reglas, las
            validaciones y los campos que sostienen los casos de borde— se
            resuelve automáticamente subiendo la cadena.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <SourceJobPicker
            jobs={jobs}
            error={error}
            value={selected}
            onChange={(id) => elegirPlan(id, "lista")}
            manualValue={manual}
            onManualChange={(v) => elegirPlan(v, "manual")}
            labels={{
              singular: "plan Scrum",
              plural: "planes Scrum",
              jobsBasePath: "/agents/scrum/jobs",
              createHref: "/agents/scrum/new",
              createLabel: "Crear un plan Scrum",
            }}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            Contrato de API{" "}
            <span className="text-sm font-normal text-muted-foreground">
              (opcional)
            </span>
          </CardTitle>
          <CardDescription>
            Con contrato se diseñan los <b>casos de autorización</b>, derivados
            de su matriz. Sin contrato el plan se genera igual, sin ellos y
            declarándolo: no se adivina quién puede ver qué.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {!scrumJobId ? (
            <p className="rounded-md border border-dashed p-3 text-sm text-muted-foreground">
              Elige primero un plan Scrum: los contratos que se ofrecen son los
              de <b>esa</b> cadena.
            </p>
          ) : contratos === null ? (
            <p className="rounded-md border p-3 text-sm text-muted-foreground">
              Buscando contratos de la cadena…
            </p>
          ) : contratos.length === 0 ? (
            <p className="rounded-md border border-dashed p-3 text-sm text-muted-foreground">
              Esta cadena no tiene ningún contrato de API todavía. El plan se
              generará sin casos de autorización.{" "}
              <Link
                href="/agents/api/new"
                className="font-medium text-primary underline-offset-2 hover:underline"
              >
                Generar el contrato primero
              </Link>
              .
            </p>
          ) : (
            <div className="space-y-1.5">
              <Label htmlFor="api-job">Contrato contra el que probar</Label>
              <NativeSelect
                id="api-job"
                value={apiJobId}
                onChange={(e) => setApiJobId(e.target.value)}
              >
                <option value="">Sin contrato (sin casos de autorización)</option>
                {contratos.map((j) => (
                  <option key={j.job_id} value={j.job_id}>
                    {j.title ? `${j.title} · ` : ""}v{j.version} · {j.job_id}
                    {j.ready_for_next_stage ? " · listo" : " · con pendientes"}
                  </option>
                ))}
              </NativeSelect>
              <p className="text-xs text-muted-foreground">
                La elección es tuya: ofrecer «el más reciente» adivinaría contra
                qué versión del contrato quieres probar.
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            Ajustes{" "}
            <span className="text-sm font-normal text-muted-foreground">
              (opcionales)
            </span>
          </CardTitle>
          <CardDescription>
            Con los valores por defecto basta. Se guardan en el artefacto para
            que el cálculo de cobertura y esfuerzo sea auditable.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="max-cases">Casos máximos por criterio</Label>
              <Input
                id="max-cases"
                type="number"
                min={1}
                max={20}
                value={maxCases}
                onChange={(e) => setMaxCases(e.target.value)}
                placeholder="6 (por defecto)"
              />
              <p className="text-xs text-muted-foreground">
                Techo contra la explosión combinatoria. Lo que se pode queda
                registrado con su id.
              </p>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="capacity">Capacidad de QA (minutos)</Label>
              <Input
                id="capacity"
                type="number"
                min={1}
                value={capacity}
                onChange={(e) => setCapacity(e.target.value)}
                placeholder="sin declarar"
              />
              <p className="text-xs text-muted-foreground">
                Si la declaras, el plan estima en cuántas sesiones cabe.
              </p>
            </div>
          </div>

          <Button
            onClick={submit}
            disabled={!scrumJobId || submitting}
            className="gap-1.5"
          >
            {submitting ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <ShieldCheck className="h-4 w-4" />
            )}
            {submitting ? "Generando…" : "Generar plan de pruebas"}
          </Button>
        </CardContent>
      </Card>
    </PageContainer>
  );
}
