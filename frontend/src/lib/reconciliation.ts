// Vocabulario visual de la reconciliación (INV4/INV5).
//
// Vive aquí y no repartido por las tres vistas de artefacto porque el veredicto
// significa lo MISMO en Arquitectura, BD y API: si cada vista eligiera su color,
// el mismo estado se leería distinto según dónde apareciera, que es justo lo que
// hace inservible un código de color.
//
// Clases literales (no plantillas `bg-${x}-100`): Tailwind necesita verlas
// escritas para incluirlas en el CSS final.

export type ReconciliationStatus = "reuse" | "extend" | "new" | "conflict";

export interface MatchedAsset {
  name: string;
  asset_id: string;
  asset_name: string;
  system_id: string;
  system_name: string;
  name_score: number;
  structure_score: number | null;
}

export interface ReconciliationRef {
  status: ReconciliationStatus;
  reason: string;
  blocking: boolean;
  matched?: MatchedAsset | null;
  missing?: string[];
}

export interface ReconciliationSummary {
  system_id: string | null;
  system_name: string | null;
  counts: Partial<Record<ReconciliationStatus, number>>;
  blocking: number;
  reconciled: number;
  total: number;
  performed: boolean;
  reason: string;
}

export interface ReconciliationStyle {
  label: string;
  /** Qué significa, en una línea. Va en el tooltip y en el panel. */
  hint: string;
  badge: string;
  dot: string;
}

export const RECONCILIATION_STYLE: Record<
  ReconciliationStatus,
  ReconciliationStyle
> = {
  reuse: {
    label: "Reutilizado",
    hint: "Ya existe en el sistema destino y sirve tal cual: no hay que construirlo.",
    badge: "bg-emerald-100 text-emerald-700 ring-emerald-200",
    dot: "bg-emerald-500",
  },
  extend: {
    label: "Extendido",
    hint: "Ya existe pero le falta algo: se modifica lo existente, no se crea de nuevo.",
    badge: "bg-blue-100 text-blue-700 ring-blue-200",
    dot: "bg-blue-500",
  },
  new: {
    label: "Nuevo",
    hint: "No existe en el sistema destino: se construye.",
    badge: "bg-violet-100 text-violet-700 ring-violet-200",
    dot: "bg-violet-500",
  },
  conflict: {
    label: "Conflicto",
    hint: "Hay algo parecido pero no se sabe si es lo mismo. Requiere una respuesta antes de construir.",
    badge: "bg-red-100 text-red-700 ring-red-200",
    dot: "bg-red-500",
  },
};

/** Orden de presentación: primero lo que reclama atención. */
export const RECONCILIATION_ORDER: ReconciliationStatus[] = [
  "conflict",
  "extend",
  "reuse",
  "new",
];

export function styleOf(status: ReconciliationStatus): ReconciliationStyle {
  return RECONCILIATION_STYLE[status];
}

/**
 * Frase de cabecera del resumen. Distingue los tres casos que NO son lo mismo:
 * la fase no corrió, corrió y no encontró nada, o corrió y reconcilió cosas.
 *
 * Confundir "no se reconcilió" con "no había nada que reconciliar" haría leer un
 * diseño como validado contra el inventario cuando nadie lo comparó con nada.
 */
export function summaryHeadline(summary: ReconciliationSummary | null): string {
  if (!summary || !summary.performed) {
    return summary?.reason || "No se reconcilió contra ningún inventario.";
  }
  if (summary.total === 0) {
    return `Sin elementos que reconciliar contra «${summary.system_name}».`;
  }
  const reutilizados = summary.reconciled;
  const base = `${reutilizados} de ${summary.total} ya existen en «${summary.system_name}»`;
  return summary.blocking > 0
    ? `${base}. ${summary.blocking} sin confirmar.`
    : `${base}.`;
}

/** Cuenta por estado, en orden de presentación y sin los que valen cero. */
export function summaryChips(
  summary: ReconciliationSummary | null,
): { status: ReconciliationStatus; count: number }[] {
  if (!summary?.performed) return [];
  return RECONCILIATION_ORDER.map((status) => ({
    status,
    count: summary.counts[status] ?? 0,
  })).filter((c) => c.count > 0);
}
