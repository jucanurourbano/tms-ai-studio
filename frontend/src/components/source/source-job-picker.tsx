"use client";

// SELECTOR DE JOB DE ORIGEN, compartido por todos los agentes encadenados.
//
// Cada agente del ISDF consume el artefacto del anterior, así que todos necesitan
// la misma pantalla: "elige el job de origen". El problema no era listar jobs,
// era que el gate del backend rechaza a casi todos y el selector no lo explicaba:
// el usuario elegía algo, recibía un 409 y no sabía qué hacer con él.
//
// Tres estados, tres tratamientos:
//
//   · **Elegibles** (semáforo verde): lo único seleccionable.
//   · **Casi listos** (terminaron, pero el gate los frena): visibles y NO
//     seleccionables, con lo que les falta y un enlace directo a lo que lo
//     resuelve. Se ven porque saber que existen —y por qué no valen— es justo la
//     información que falta; no se pueden elegir porque elegirlos solo produce un
//     error.
//   · **Fallidos y en curso**: no llegan hasta aquí. Los filtra el backend
//     (`USABLE_JOB_STATUSES`): no tienen artefacto que consumir.
//
// Las reglas (qué es elegible, qué decir cuando no hay nada) viven en
// `lib/source-jobs.ts` para poder testearse sin montar la interfaz.

import { ArrowRight, CircleAlert, Plus } from "lucide-react";
import Link from "next/link";

import { JobStatusBadge, Mono } from "@/components/ef/badges";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { plural } from "@/lib/artifact-search";
import {
  blockedReasonOf,
  emptyStateFor,
  partitionSourceJobs,
  unblockHref,
  type SourceJob,
  type SourceJobPickerLabels,
} from "@/lib/source-jobs";
import { cn } from "@/lib/utils";

export type { SourceJob, SourceJobPickerLabels };

export function SourceJobPicker({
  jobs,
  labels,
  value,
  onChange,
  manualValue,
  onManualChange,
  error,
}: {
  /** `null` mientras carga. */
  jobs: SourceJob[] | null;
  labels: SourceJobPickerLabels;
  /** Id elegido de la lista (cadena vacía si ninguno). */
  value: string;
  onChange: (jobId: string) => void;
  /** Id pegado a mano (escape hatch; el gate del backend lo valida igual). */
  manualValue: string;
  onManualChange: (value: string) => void;
  error?: string | null;
}) {
  const { eligible, almostReady } = partitionSourceJobs(jobs ?? []);

  return (
    <div className="space-y-4">
      {error && <div className="text-sm text-red-600">{error}</div>}

      {jobs === null ? (
        <div className="rounded-md border p-3 text-sm text-muted-foreground">
          Cargando…
        </div>
      ) : eligible.length > 0 ? (
        <div className="max-h-72 divide-y overflow-y-auto rounded-md border">
          {eligible.map((j) => (
            <EligibleRow
              key={j.job_id}
              job={j}
              active={value === j.job_id}
              onSelect={() => onChange(j.job_id)}
            />
          ))}
        </div>
      ) : (
        <EmptyState jobs={jobs} labels={labels} />
      )}

      {almostReady.length > 0 && (
        <section className="space-y-2">
          <div className="flex items-baseline gap-2">
            <h3 className="text-sm font-medium">Casi listos</h3>
            <span className="text-xs text-muted-foreground">
              terminaron, pero el gate los frena
            </span>
          </div>
          <div className="divide-y rounded-md border border-dashed bg-muted/20">
            {almostReady.map((j) => (
              <AlmostReadyRow key={j.job_id} job={j} labels={labels} />
            ))}
          </div>
        </section>
      )}

      <div className="space-y-1.5">
        <Label htmlFor="manual">…o pega un id de {labels.singular}</Label>
        <Input
          id="manual"
          value={manualValue}
          onChange={(e) => onManualChange(e.target.value)}
          placeholder="01…"
          className="font-mono text-xs"
        />
      </div>
    </div>
  );
}

function JobTitle({ job }: { job: SourceJob }) {
  return (
    <span className="min-w-0 flex-1 truncate">
      {job.title ? (
        <>
          <span className="font-medium">{job.title}</span>{" "}
          <Mono className="text-[10px]">{job.job_id}</Mono>
        </>
      ) : (
        <Mono>{job.job_id}</Mono>
      )}
    </span>
  );
}

function EligibleRow({
  job,
  active,
  onSelect,
}: {
  job: SourceJob;
  active: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={active}
      className={cn(
        "flex w-full items-center gap-2 p-2 text-left text-sm transition-colors",
        active ? "bg-accent" : "hover:bg-muted/50",
      )}
    >
      <JobTitle job={job} />
      <JobStatusBadge status={job.status} />
      <span className="shrink-0 text-xs text-emerald-700">listo ✓</span>
    </button>
  );
}

/**
 * Un job que terminó pero no pasa el gate. No es un botón a propósito: no se
 * puede seleccionar, y el único control que ofrece es el que lo desbloquea.
 */
function AlmostReadyRow({
  job,
  labels,
}: {
  job: SourceJob;
  labels: SourceJobPickerLabels;
}) {
  const porPreguntas = blockedReasonOf(job) === "blocking_questions";
  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1 p-2 text-sm text-muted-foreground">
      <JobTitle job={job} />
      <JobStatusBadge status={job.status} />
      <span className="inline-flex shrink-0 items-center gap-1 text-xs text-amber-700">
        <CircleAlert className="h-3.5 w-3.5" />
        {porPreguntas
          ? plural(
              job.blocking_pending.length,
              "pregunta bloqueante",
              "preguntas bloqueantes",
            )
          : "no cumple el contenido mínimo"}
      </span>
      <Link
        href={unblockHref(job, labels.jobsBasePath)}
        className="inline-flex shrink-0 items-center gap-1 text-xs font-medium text-primary underline-offset-2 hover:underline"
      >
        {porPreguntas ? "Responder preguntas" : "Revisar"}
        <ArrowRight className="h-3 w-3" />
      </Link>
    </div>
  );
}

/** Sin nada elegible: el motivo más probable y la acción que lo resuelve. */
function EmptyState({
  jobs,
  labels,
}: {
  jobs: SourceJob[];
  labels: SourceJobPickerLabels;
}) {
  const { title, reason, cta } = emptyStateFor(jobs, labels);
  const esCrear = cta.href === labels.createHref;

  return (
    <div className="rounded-md border border-dashed p-4 text-sm">
      <p className="font-medium">{title}</p>
      <p className="mt-1 text-muted-foreground">{reason}</p>
      <Link
        href={cta.href}
        className="mt-3 inline-flex items-center gap-1 text-sm font-medium text-primary underline-offset-2 hover:underline"
      >
        {esCrear && <Plus className="h-3.5 w-3.5" />}
        {cta.label}
        {!esCrear && <ArrowRight className="h-3.5 w-3.5" />}
      </Link>
    </div>
  );
}
