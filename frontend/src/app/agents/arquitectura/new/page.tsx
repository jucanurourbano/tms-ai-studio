"use client";

import { Layers, Loader2 } from "lucide-react";
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
import { arquitecturaApi } from "@/lib/api/arquitectura";
import { ApiError } from "@/lib/api/client";
import type { AvailableScrumJob } from "@/lib/types/arquitectura";

export default function NewDesignPage() {
  const router = useRouter();
  const [jobs, setJobs] = useState<AvailableScrumJob[] | null>(null);
  const [selected, setSelected] = useState<string>("");
  const [manual, setManual] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    arquitecturaApi
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

  async function submit() {
    if (!scrumJobId) {
      toast.error("Elige un plan Scrum listo o pega su id.");
      return;
    }
    setSubmitting(true);
    try {
      const result = await arquitecturaApi.createDesign(scrumJobId);
      toast.success("Diseño de arquitectura iniciado");
      router.push(`/agents/arquitectura/jobs/${result.job_id}`);
    } catch (err) {
      toast.error("No se pudo generar el diseño", {
        description: err instanceof ApiError ? err.message : undefined,
      });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <PageContainer variant="form">
      <PageHeader
        module="arquitectura"
        icon="layers"
        eyebrow="Diseñar"
        title="Nuevo diseño de arquitectura"
        description={
          <>
            Elige un plan Scrum <b>listo</b> (semáforo en verde) como origen.
          </>
        }
      />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Plan Scrum de origen</CardTitle>
          <CardDescription>
            Solo los planes listos habilitan el diseño (gate de entrada). El EF de
            origen se resuelve automáticamente.
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
              singular: "plan Scrum",
              plural: "planes Scrum",
              jobsBasePath: "/agents/scrum/jobs",
              createHref: "/agents/scrum/new",
              createLabel: "Crear un plan ágil",
            }}
          />

          <Button
            onClick={submit}
            disabled={!scrumJobId || submitting}
            className="gap-1.5"
          >
            {submitting ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Layers className="h-4 w-4" />
            )}
            {submitting ? "Generando…" : "Generar diseño"}
          </Button>
        </CardContent>
      </Card>
    </PageContainer>
  );
}
