"use client";

import { Database, Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { JobStatusBadge, Mono } from "@/components/ef/badges";
import { PageContainer } from "@/components/shell/page-container";
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
import { bdApi } from "@/lib/api/bd";
import { ApiError } from "@/lib/api/client";
import type { AvailableArchitectureJob, DbEngine } from "@/lib/types/bd";
import { cn } from "@/lib/utils";

const ENGINES: { value: DbEngine | ""; label: string }[] = [
  { value: "", label: "El que decidió la arquitectura" },
  { value: "postgresql", label: "PostgreSQL (estándar de la casa)" },
  { value: "sqlserver", label: "SQL Server" },
  { value: "oracle", label: "Oracle" },
  { value: "mysql", label: "MySQL" },
];

export default function NewDatabaseModelPage() {
  const router = useRouter();
  const [jobs, setJobs] = useState<AvailableArchitectureJob[] | null>(null);
  const [selected, setSelected] = useState<string>("");
  const [manual, setManual] = useState("");
  const [engine, setEngine] = useState<DbEngine | "">("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    bdApi
      .availableArchitectureJobs()
      .then((d) => setJobs(d.items))
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "No se pudo cargar."),
      );
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const architectureJobId = (selected || manual).trim();

  async function submit() {
    if (!architectureJobId) {
      toast.error("Elige un diseño de arquitectura listo o pega su id.");
      return;
    }
    setSubmitting(true);
    try {
      const result = await bdApi.createModel(
        architectureJobId,
        engine || undefined,
      );
      toast.success("Modelo de datos iniciado");
      router.push(`/agents/bd/jobs/${result.job_id}`);
    } catch (err) {
      toast.error("No se pudo generar el modelo", {
        description: err instanceof ApiError ? err.message : undefined,
      });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <PageContainer variant="form">
      <PageHeader
        module="bd"
        icon="database"
        eyebrow="Diseñar"
        title="Nuevo modelo de datos"
        description={
          <>
            Elige un diseño de arquitectura <b>listo</b> (semáforo en verde) como
            origen.
          </>
        }
      />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Diseño de arquitectura</CardTitle>
          <CardDescription>
            Solo los diseños listos habilitan el modelado (gate de entrada). El EF
            de origen, que es la materia prima del modelo, se resuelve
            automáticamente subiendo la cadena.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {error && <div className="text-sm text-red-600">{error}</div>}

          <div className="max-h-72 divide-y overflow-y-auto rounded-md border">
            {jobs === null ? (
              <div className="p-3 text-sm text-muted-foreground">Cargando…</div>
            ) : jobs.length === 0 ? (
              <div className="p-3 text-sm text-muted-foreground">
                No hay diseños de arquitectura. Crea uno en el Agente Arquitectura
                primero.
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
            <Label htmlFor="manual">…o pega un id de job de Arquitectura</Label>
            <Input
              id="manual"
              value={manual}
              onChange={(e) => {
                setManual(e.target.value);
                setSelected("");
              }}
              placeholder="01AR…"
              className="font-mono text-xs"
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="engine">Motor de base de datos</Label>
            <select
              id="engine"
              value={engine}
              onChange={(e) => setEngine(e.target.value as DbEngine | "")}
              className="w-full rounded-md border bg-background px-3 py-2 text-sm"
            >
              {ENGINES.map((e) => (
                <option key={e.value} value={e.value}>
                  {e.label}
                </option>
              ))}
            </select>
            <p className="text-xs text-muted-foreground">
              Solo hace falta elegirlo si la arquitectura no fijó motor, o si
              quieres modelar sobre otro sin esperar a corregir el diseño. El DDL
              se puede volver a generar en cualquier motor después, sin coste.
            </p>
          </div>

          <Button
            onClick={submit}
            disabled={!architectureJobId || submitting}
            className="gap-1.5"
          >
            {submitting ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Database className="h-4 w-4" />
            )}
            {submitting ? "Generando…" : "Generar modelo de datos"}
          </Button>
        </CardContent>
      </Card>
    </PageContainer>
  );
}
