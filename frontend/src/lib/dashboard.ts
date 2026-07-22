// Utilidades puras del dashboard (sin dependencias de React): unión de la
// actividad reciente EF+Scrum, semáforo compacto por estado, y métricas del mes.
// Aparte para poder testearlas de forma determinista.

import type { JobListItem, JobStatus } from "@/lib/types/ef";
import type { ScrumJobListItem } from "@/lib/types/scrum";

export type AgentKind = "ef" | "scrum";

/** Fila unificada de la franja de actividad (EF o Scrum). */
export interface ActivityRow {
  job_id: string;
  agent: AgentKind;
  title?: string | null;
  status: JobStatus;
  created_at?: string | null;
  /** Enlace al detalle del job según el agente. */
  href: string;
}

export type Semaforo = "green" | "amber" | "red" | "blue";

/**
 * Semáforo compacto derivado del estado del job:
 * verde = completado, ámbar = avisos / requiere datos, rojo = falló,
 * azul = en proceso / pendiente.
 */
export function semaforoFor(status: JobStatus): Semaforo {
  switch (status) {
    case "COMPLETED":
      return "green";
    case "COMPLETED_WITH_WARNINGS":
    case "NEEDS_INPUT":
      return "amber";
    case "FAILED":
      return "red";
    default:
      return "blue";
  }
}

function toMillis(iso?: string | null): number {
  if (!iso) return -Infinity;
  const t = Date.parse(iso);
  return Number.isNaN(t) ? -Infinity : t;
}

/**
 * Une los jobs de EF y Scrum en una sola lista ordenada por fecha de creación
 * (más reciente primero). Los ítems sin fecha válida quedan al final.
 */
export function mergeActivity(
  ef: JobListItem[],
  scrum: ScrumJobListItem[],
): ActivityRow[] {
  const rows: ActivityRow[] = [
    ...ef.map((j) => ({
      job_id: j.job_id,
      agent: "ef" as const,
      title: j.title,
      status: j.status,
      created_at: j.created_at,
      href: `/agents/ef/jobs/${j.job_id}`,
    })),
    ...scrum.map((j) => ({
      job_id: j.job_id,
      agent: "scrum" as const,
      title: j.title,
      status: j.status,
      created_at: j.created_at,
      href: `/agents/scrum/jobs/${j.job_id}`,
    })),
  ];
  return rows.sort((a, b) => toMillis(b.created_at) - toMillis(a.created_at));
}

/** ¿La fecha ISO cae en el mismo mes y año que `nowMs`? */
export function isSameMonth(
  iso?: string | null,
  nowMs: number = Date.now(),
): boolean {
  if (!iso) return false;
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return false;
  const d = new Date(t);
  const now = new Date(nowMs);
  return (
    d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth()
  );
}

/** Cuenta las filas creadas en el mes actual. */
export function countThisMonth(
  rows: { created_at?: string | null }[],
  nowMs: number = Date.now(),
): number {
  return rows.filter((r) => isSameMonth(r.created_at, nowMs)).length;
}

const USD = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/**
 * Formatea un costo en USD para lectura ("$0.42", "$12.30", "$1,204.00").
 * Costos positivos por debajo de un centavo se muestran como "<$0.01".
 */
export function formatCost(usd?: number | null): string {
  if (usd === null || usd === undefined || Number.isNaN(usd)) return "$0.00";
  if (usd > 0 && usd < 0.01) return "<$0.01";
  return USD.format(usd);
}
