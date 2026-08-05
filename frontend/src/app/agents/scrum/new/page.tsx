"use client";

import { Loader2, Sparkles } from "lucide-react";
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
import { ApiError } from "@/lib/api/client";
import { scrumApi } from "@/lib/api/scrum";
import type { AvailableEfJob } from "@/lib/types/scrum";

export default function NewPlanPage() {
  const router = useRouter();
  const [jobs, setJobs] = useState<AvailableEfJob[] | null>(null);
  const [selected, setSelected] = useState<string>("");
  const [manual, setManual] = useState("");
  const [capacity, setCapacity] = useState("20");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    scrumApi
      .availableEfJobs()
      .then((d) => setJobs(d.items))
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "No se pudo cargar."),
      );
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const efJobId = (selected || manual).trim();
  const capacityNum = Number(capacity);
  const capacityValid = Number.isInteger(capacityNum) && capacityNum >= 1;

  async function submit() {
    if (!efJobId) {
      toast.error("Elige un análisis EF listo o pega su id.");
      return;
    }
    setSubmitting(true);
    try {
      const result = await scrumApi.createPlan(
        efJobId,
        capacityValid ? capacityNum : undefined,
      );
      toast.success("Planificación iniciada");
      router.push(`/agents/scrum/jobs/${result.job_id}`);
    } catch (err) {
      toast.error("No se pudo generar el plan", {
        description: err instanceof ApiError ? err.message : undefined,
      });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <PageContainer variant="form">
      <PageHeader
        module="scrum"
        icon="kanban"
        eyebrow="Gestionar"
        title="Nuevo plan ágil"
        description={
          <>
            Elige un análisis EF <b>listo</b> (semáforo en verde) como origen.
          </>
        }
      />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Análisis EF de origen</CardTitle>
          <CardDescription>
            Solo los EF listos habilitan la planificación (gate de entrada).
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
              singular: "análisis EF",
              plural: "análisis EF",
              jobsBasePath: "/agents/ef/jobs",
              createHref: "/agents/ef/new",
              createLabel: "Crear un análisis EF",
            }}
          />

          <div className="space-y-1.5 max-w-40">
            <Label htmlFor="capacity">Capacidad por sprint (puntos)</Label>
            <Input
              id="capacity"
              type="number"
              min={1}
              value={capacity}
              onChange={(e) => setCapacity(e.target.value)}
            />
          </div>

          <Button
            onClick={submit}
            disabled={!efJobId || submitting}
            className="gap-1.5"
          >
            {submitting ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Sparkles className="h-4 w-4" />
            )}
            {submitting ? "Generando…" : "Generar plan"}
          </Button>
        </CardContent>
      </Card>
    </PageContainer>
  );
}
