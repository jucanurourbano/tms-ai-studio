// Reglas del selector de job de origen, separadas de su pintura.
//
// Qué se puede elegir, qué se muestra frenado y qué decir cuando no hay nada son
// **decisiones**, no maquetación: viven aquí para poder testearlas sin montar la
// interfaz, igual que la cascada de asignaciones del Scrum.
//
// La regla de fondo: el gate del backend ya decide qué es consumible. El selector
// no lo reinterpreta — lo **explica**, y evita que el usuario elija algo que va a
// ser rechazado.

import type { JobStatus } from "@/lib/types/ef";

/** Forma común de los endpoints `available-*-jobs` de todos los agentes. */
export interface SourceJob {
  job_id: string;
  title?: string | null;
  status: JobStatus;
  ready_for_next_stage: boolean;
  blocking_pending: string[];
}

export interface SourceJobPickerLabels {
  /** "diseño de arquitectura", "análisis EF", "plan Scrum"… */
  singular: string;
  /** "diseños de arquitectura", "análisis EF", "planes Scrum"… */
  plural: string;
  /** Ruta base de los jobs de ese agente: `/agents/arquitectura/jobs`. */
  jobsBasePath: string;
  /** Qué hacer si no existe ninguno: crear el eslabón anterior de la cadena. */
  createHref: string;
  createLabel: string;
}

/** Por qué un job terminado no se puede elegir. */
export type BlockedReason = "blocking_questions" | "minimum_content";

export interface SourceJobGroups {
  /** Semáforo verde: lo único seleccionable. */
  eligible: SourceJob[];
  /** Terminados pero frenados por el gate: visibles, no seleccionables. */
  almostReady: SourceJob[];
}

/**
 * Reparte los jobs en elegibles y "casi listos".
 *
 * No filtra por estado: los fallidos y en curso **no deben llegar aquí**, los
 * descarta el backend (`USABLE_JOB_STATUSES`) porque no tienen artefacto que
 * consumir. Si alguno se colara, este reparto lo dejaría en "casi listos", que es
 * el lado seguro: visible pero no seleccionable.
 */
export function partitionSourceJobs(jobs: SourceJob[]): SourceJobGroups {
  return {
    eligible: jobs.filter((j) => j.ready_for_next_stage),
    almostReady: jobs.filter((j) => !j.ready_for_next_stage),
  };
}

/** Por qué está frenado: preguntas sin responder, o contenido mínimo del gate. */
export function blockedReasonOf(job: SourceJob): BlockedReason {
  return job.blocking_pending.length > 0
    ? "blocking_questions"
    : "minimum_content";
}

/**
 * Enlace que **resuelve** el bloqueo de ese job.
 *
 * Con preguntas pendientes lleva al panel de preguntas del centro de comando
 * (deep-link por hash); si el freno es el contenido mínimo no hay nada que
 * responder, así que lleva al artefacto a revisarlo.
 */
export function unblockHref(job: SourceJob, jobsBasePath: string): string {
  const base = `${jobsBasePath}/${job.job_id}`;
  return blockedReasonOf(job) === "blocking_questions"
    ? `${base}#preguntas`
    : base;
}

export interface SourceEmptyState {
  title: string;
  /** El motivo MÁS PROBABLE de que no haya nada elegible. */
  reason: string;
  cta: { href: string; label: string };
}

/**
 * Qué decir cuando no hay ningún job elegible.
 *
 * Distingue los dos casos que el usuario vive de forma distinta: "hay candidatos
 * pero les falta algo" (acción: desbloquear ese candidato) y "no hay nada"
 * (acción: crear el eslabón anterior de la cadena). Un estado vacío que no
 * distinga los dos manda al usuario a crear otro job cuando ya tenía uno a una
 * respuesta de estar listo.
 */
export function emptyStateFor(
  jobs: SourceJob[],
  labels: SourceJobPickerLabels,
): SourceEmptyState {
  const { almostReady } = partitionSourceJobs(jobs);
  const conPreguntas = almostReady.filter(
    (j) => blockedReasonOf(j) === "blocking_questions",
  );
  const candidato = conPreguntas[0] ?? almostReady[0];
  const title = `Aún no hay ${labels.plural} listos`;

  if (!candidato) {
    return {
      title,
      reason:
        `No hay ningún ${labels.singular} terminado todavía. Es el paso previo ` +
        "de la cadena: hay que generarlo antes de poder continuar.",
      cta: { href: labels.createHref, label: labels.createLabel },
    };
  }

  const cuantos = almostReady.length;
  const sustantivo =
    cuantos === 1
      ? `${labels.singular} terminado`
      : `${labels.plural} terminados`;

  if (conPreguntas.length > 0) {
    return {
      title,
      reason:
        `Hay ${cuantos} ${sustantivo}, pero ` +
        `${conPreguntas.length === 1 ? "tiene" : "tienen"} preguntas bloqueantes ` +
        "sin responder. Respóndelas y el semáforo se pone en verde.",
      cta: {
        href: unblockHref(candidato, labels.jobsBasePath),
        label: "Responder preguntas",
      },
    };
  }

  return {
    title,
    reason:
      `Hay ${cuantos} ${sustantivo}, pero ` +
      `${cuantos === 1 ? "no cumple" : "no cumplen"} el contenido mínimo del ` +
      "gate. Ábrelo para ver qué falta.",
    cta: { href: unblockHref(candidato, labels.jobsBasePath), label: "Revisar" },
  };
}
