"use client";

import { Layers, Loader2 } from "lucide-react";
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
import { arquitecturaApi } from "@/lib/api/arquitectura";
import { ApiError } from "@/lib/api/client";
import type { AvailableScrumJob } from "@/lib/types/arquitectura";
import { cn } from "@/lib/utils";

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
    <div className="mx-auto max-w-5xl p-6">
      <PageHeader
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
          {error && <div className="text-sm text-red-600">{error}</div>}

          <div className="max-h-72 divide-y overflow-y-auto rounded-md border">
            {jobs === null ? (
              <div className="p-3 text-sm text-muted-foreground">Cargando…</div>
            ) : jobs.length === 0 ? (
              <div className="p-3 text-sm text-muted-foreground">
                No hay planes Scrum. Crea uno en el Agente Scrum primero.
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
            <Label htmlFor="manual">…o pega un id de job Scrum</Label>
            <Input
              id="manual"
              value={manual}
              onChange={(e) => {
                setManual(e.target.value);
                setSelected("");
              }}
              placeholder="01SC…"
              className="font-mono text-xs"
            />
          </div>

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
    </div>
  );
}
