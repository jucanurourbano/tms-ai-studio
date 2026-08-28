// Vocabulario y formato del control de gasto (GAS2).
//
// Vive aquí y no dentro de la página por la misma razón que
// `lib/reconciliation.ts`: son decisiones sobre cómo se lee un número —cuántos
// decimales, qué significa "mixto", contra qué tope se compara— y son
// comprobables sin montar la pantalla.
//
// Clases literales (no plantillas `bg-${x}-100`): Tailwind necesita verlas
// escritas para incluirlas en el CSS final.

import type { TotalUsageSource } from "@/lib/types/gasto";

/**
 * Importe en USD desde la cadena de seis decimales que manda el backend.
 *
 * Dos precisiones a propósito, y no por inconsistencia: los totales se leen en
 * céntimos, pero una fila del desglose por nodo puede valer 0,003 USD y a dos
 * decimales se leería `0,00` — justo la fila que tiene que enseñar el
 * antes/después de recortar un nodo. Cada columna usa una sola precisión.
 */
export function formatUsd(value: string, decimals: number = 2): string {
  // `Number("")` es 0, y un importe ausente no es un importe de cero: la misma
  // regla que en el backend impide anotar 0 cuando falta el `usage`.
  if (typeof value !== "string" || value.trim() === "") return "—";
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  return `$${n.toLocaleString("es-PE", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })}`;
}

/** Porcentaje, o `—` cuando no existe (tope en 0). */
export function formatPct(pct: number | null): string {
  return pct === null ? "—" : `${pct.toLocaleString("es-PE")}%`;
}

export function formatCount(n: number): string {
  return n.toLocaleString("es-PE");
}

export interface UsageSourceStyle {
  label: string;
  /** Qué implica para quien lee la cifra, en una línea. */
  hint: string;
  badge: string;
}

/**
 * Qué clase de dato es el total. Se muestra SIEMPRE, también cuando es `real`:
 * un sello que solo aparece cuando algo va mal enseña a ignorarlo, y su ausencia
 * se confunde con "no se comprobó".
 */
export const USAGE_SOURCE_STYLE: Record<TotalUsageSource, UsageSourceStyle> = {
  real: {
    label: "Medido",
    hint: "Todas las llamadas del mes traen el consumo que reportó el proveedor.",
    badge: "border-emerald-300 bg-emerald-50 text-emerald-700",
  },
  mixto: {
    label: "Parcialmente estimado",
    hint: "Algunas llamadas no devolvieron su consumo y se anotaron con una estimación: la cifra del mes es aproximada por esa parte.",
    badge: "border-amber-300 bg-amber-50 text-amber-700",
  },
  estimado: {
    label: "Estimado",
    hint: "Ninguna llamada del mes devolvió su consumo real. Toda la cifra es una estimación.",
    badge: "border-orange-300 bg-orange-50 text-orange-700",
  },
  sin_datos: {
    label: "Sin datos",
    hint: "Todavía no hay ninguna llamada anotada en este mes.",
    badge: "border-slate-300 bg-slate-50 text-slate-600",
  },
};

/**
 * Cómo nombrar el gasto que ningún nodo reclama.
 *
 * Los nodos que no son *map* no llevan etiqueta y su gasto llega con
 * `stage: null`. Se nombra en la vista y no en la API a propósito: ponerle
 * nombre allí lo convertiría en un nodo más del grafo, y no lo es.
 */
export function stageLabel(stage?: string | null): string {
  return stage ?? "Sin nodo atribuido";
}

/** `true` si la fila es el gasto no atribuido, para distinguirla al pintarla. */
export function isUnattributed(stage?: string | null): boolean {
  return stage === null || stage === undefined;
}

/**
 * Color del avance contra un tope. Los cortes se leen sobre el OBJETIVO, no
 * sobre el techo: el objetivo es el número contra el que hay que comparar, y
 * esperar al 80% del techo duro para teñir de rojo avisaría cuando ya no queda
 * margen para reaccionar.
 */
export function progressTone(pct: number | null): string {
  if (pct === null) return "bg-slate-400";
  if (pct >= 100) return "bg-red-500";
  if (pct >= 80) return "bg-amber-500";
  return "bg-emerald-500";
}

/** Ancho de la barra, acotado a [0, 100]: pasarse del tope no desborda la caja. */
export function progressWidth(pct: number | null): string {
  if (pct === null) return "0%";
  return `${Math.min(100, Math.max(0, pct))}%`;
}
