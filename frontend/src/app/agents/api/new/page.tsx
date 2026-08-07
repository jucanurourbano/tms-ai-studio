"use client";

import { Loader2, Plug } from "lucide-react";
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
import { apisApi } from "@/lib/api/apis";
import { ApiError } from "@/lib/api/client";
import type { AvailableBdJob } from "@/lib/types/api";

export default function NewApiSpecPage() {
  const router = useRouter();
  const [jobs, setJobs] = useState<AvailableBdJob[] | null>(null);
  const [selected, setSelected] = useState<string>("");
  const [manual, setManual] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    apisApi
      .availableBdJobs()
      .then((d) => setJobs(d.items))
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "No se pudo cargar."),
      );
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const bdJobId = (selected || manual).trim();

  async function submit() {
    if (!bdJobId) {
      toast.error("Elige un modelo de datos listo o pega su id.");
      return;
    }
    setSubmitting(true);
    try {
      const result = await apisApi.createSpec(bdJobId);
      toast.success("Especificación de API iniciada");
      router.push(`/agents/api/jobs/${result.job_id}`);
    } catch (err) {
      toast.error("No se pudo generar la especificación", {
        description: err instanceof ApiError ? err.message : undefined,
      });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <PageContainer variant="form">
      <PageHeader
        module="api"
        icon="plug"
        eyebrow="Construir"
        title="Nueva especificación de API"
        description={
          <>
            Elige un modelo de datos <b>listo</b> (semáforo en verde) como origen.
          </>
        }
      />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Modelo de datos</CardTitle>
          <CardDescription>
            Solo los modelos listos habilitan la especificación (gate de entrada).
            El EF de origen —de donde salen los actores, la matriz CRUD y las
            reglas— y la arquitectura se resuelven automáticamente subiendo la
            cadena.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <SourceJobPicker
            jobs={jobs}
            error={error}
            value={selected}
            onChange={(id) => {
              setSelected(id);
              setManual("");
            }}
            manualValue={manual}
            onManualChange={(v) => {
              setManual(v);
              setSelected("");
            }}
            labels={{
              singular: "modelo de datos",
              plural: "modelos de datos",
              jobsBasePath: "/agents/bd/jobs",
              createHref: "/agents/bd/new",
              createLabel: "Crear un modelo de datos",
            }}
          />

          <p className="text-xs text-muted-foreground">
            El estilo de API sale de la arquitectura. Si no lo decidió, se
            especifica REST —el estándar de la casa— y queda una pregunta al líder
            técnico para confirmarlo.
          </p>

          <Button
            onClick={submit}
            disabled={!bdJobId || submitting}
            className="gap-1.5"
          >
            {submitting ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Plug className="h-4 w-4" />
            )}
            {submitting ? "Generando…" : "Generar especificación de API"}
          </Button>
        </CardContent>
      </Card>
    </PageContainer>
  );
}
