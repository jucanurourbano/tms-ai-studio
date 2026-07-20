// Utilidades de formato puras (sin dependencias de React) para el historial de
// jobs. Se mantienen aparte para poder testearlas de forma determinista.

import type { SourceType } from "@/lib/types/ef";

/**
 * Fecha relativa en español: "hace un momento", "hace 2 min", "hace 3 h",
 * "hace 5 d", "hace 2 meses", "hace 1 año". ``nowMs`` se inyecta en tests para
 * un resultado determinista (por defecto, ``Date.now()``).
 */
export function relativeTime(
  iso?: string | null,
  nowMs: number = Date.now(),
): string {
  if (!iso) return "—";
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return "—";

  const diffSec = Math.max(0, Math.round((nowMs - then) / 1000));
  if (diffSec < 45) return "hace un momento";

  const diffMin = Math.round(diffSec / 60);
  if (diffMin < 60) return `hace ${diffMin} min`;

  const diffH = Math.round(diffMin / 60);
  if (diffH < 24) return `hace ${diffH} h`;

  const diffD = Math.round(diffH / 24);
  if (diffD < 30) return `hace ${diffD} d`;

  const diffMo = Math.round(diffD / 30);
  if (diffMo < 12) return `hace ${diffMo} ${diffMo === 1 ? "mes" : "meses"}`;

  const diffY = Math.round(diffMo / 12);
  return `hace ${diffY} ${diffY === 1 ? "año" : "años"}`;
}

/** Fecha absoluta legible (para el ``title``/tooltip de la celda). */
export function absoluteTime(iso?: string | null): string {
  if (!iso) return "";
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return "";
  return new Date(t).toLocaleString("es-PE");
}

/** Etiqueta en español del tipo de fuente. */
export function sourceLabel(source?: SourceType | null): string {
  if (source === "document") return "Documento";
  if (source === "text") return "Texto";
  return "—";
}

/**
 * Filtro client-side por título (buscador simple del historial, v1). También
 * coincide contra el id del job para permitir pegar un id. Sin query devuelve
 * todos los ítems tal cual.
 */
export function filterByTitle<
  T extends { title?: string | null; job_id: string },
>(items: T[], query: string): T[] {
  const q = query.trim().toLowerCase();
  if (!q) return items;
  return items.filter(
    (it) =>
      (it.title ?? "").toLowerCase().includes(q) ||
      it.job_id.toLowerCase().includes(q),
  );
}
