"use client";

import { Loader2, Sparkles } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { JobStatusBadge, Mono } from "@/components/ef/badges";
import { PageHeader } from "@/components/shell/page-header";
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
import { cn } from "@/lib/utils";

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
    <div className="mx-auto max-w-3xl p-6">
      <PageHeader
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
          {error && <div className="text-sm text-red-600">{error}</div>}

          <div className="rounded-md border divide-y max-h-72 overflow-y-auto">
            {jobs === null ? (
              <div className="p-3 text-sm text-muted-foreground">Cargando…</div>
            ) : jobs.length === 0 ? (
              <div className="p-3 text-sm text-muted-foreground">
                No hay análisis EF. Crea uno en el Agente EF primero.
              </div>
            ) : (
              jobs.map((j) => {
                const disabled = !j.ready_for_next_stage;
                const active = selected === j.job_id;
                return (
                  <button
                    key={j.job_id}
                    type="button"
                    disabled={disabled}
                    onClick={() => {
                      setSelected(j.job_id);
                      setManual("");
                    }}
                    className={cn(
                      "flex w-full items-center gap-2 p-2 text-left text-sm",
                      active && "bg-accent",
                      disabled
                        ? "cursor-not-allowed opacity-60"
                        : "hover:bg-muted/50",
                    )}
                  >
                    <Mono>{j.job_id}</Mono>
                    <JobStatusBadge status={j.status} />
                    <span className="ml-auto text-xs">
                      {j.ready_for_next_stage ? (
                        <span className="text-emerald-700">listo ✓</span>
                      ) : (
                        <span className="text-amber-600">
                          {j.blocking_pending.length} bloqueantes
                        </span>
                      )}
                    </span>
                  </button>
                );
              })
            )}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="manual">…o pega un id de job EF</Label>
            <Input
              id="manual"
              value={manual}
              onChange={(e) => {
                setManual(e.target.value);
                setSelected("");
              }}
              placeholder="01EF…"
              className="font-mono text-xs"
            />
          </div>

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
    </div>
  );
}
