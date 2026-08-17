// Vocabulario visual del plan de pruebas: tipo de caso, prioridad y cobertura.
//
// Vive aquí, y no repartido por la vista, por la misma razón que
// `reconciliation.ts`: el tipo de un caso significa lo MISMO en la tarjeta del
// hub, en la lista, en la matriz de trazabilidad y en el PDF. Si cada sitio
// eligiera su color, "borde" se leería distinto según dónde apareciera, que es
// justo lo que hace inservible un código de color.
//
// Y hay una razón propia de este agente: los cuatro tipos NO son una taxonomía
// decorativa. Cada uno tiene una fuente distinta y por eso un cortafuegos
// distinto —el funcional sale del criterio Gherkin, el de borde exige un límite
// citado verbatim, el de autorización no existe sin contrato de API—. El `hint`
// de cada uno dice de dónde sale, porque quien revisa el plan necesita saber qué
// respalda cada caso, no solo cómo se llama.
//
// Clases literales (no plantillas `bg-${x}-100`): Tailwind necesita verlas
// escritas para incluirlas en el CSS final.

import type {
  CoverageStatus,
  TestCaseType,
  TestPriority,
} from "@/lib/types/qa";

export interface KindStyle {
  label: string;
  /** Plural, para conteos y pestañas. */
  plural: string;
  /** De dónde sale este tipo de caso, en una línea. Tooltip y leyenda. */
  hint: string;
  badge: string;
  dot: string;
}

export const TEST_CASE_KIND: Record<TestCaseType, KindStyle> = {
  functional: {
    label: "Funcional",
    plural: "Funcionales",
    hint: "Camino feliz: el criterio de aceptación se cumple tal como está redactado.",
    badge: "bg-emerald-100 text-emerald-700 ring-emerald-200",
    dot: "bg-emerald-500",
  },
  negative: {
    label: "Negativo",
    plural: "Negativos",
    hint: "El sistema debe rechazar: dato inválido, estado incorrecto o paso omitido.",
    badge: "bg-orange-100 text-orange-700 ring-orange-200",
    dot: "bg-orange-500",
  },
  boundary: {
    label: "Borde",
    plural: "De borde",
    hint: "Frontera de una validación. Exige el límite citado verbatim: sin la frase, el límite sería una invención.",
    badge: "bg-sky-100 text-sky-700 ring-sky-200",
    dot: "bg-sky-500",
  },
  authorization: {
    label: "Autorización",
    plural: "De autorización",
    hint: "Un actor intenta lo que su alcance no permite. Se deriva de la matriz del contrato de API; sin contrato no existe.",
    badge: "bg-violet-100 text-violet-700 ring-violet-200",
    dot: "bg-violet-500",
  },
};

/** Orden de presentación: el del pipeline que los produce. */
export const TEST_CASE_KIND_ORDER: TestCaseType[] = [
  "functional",
  "negative",
  "boundary",
  "authorization",
];

export function kindStyleOf(type: TestCaseType): KindStyle {
  return TEST_CASE_KIND[type];
}

export interface PriorityStyle {
  label: string;
  badge: string;
}

/**
 * Prioridad heredada del MoSCoW de la historia, con el suelo de los casos de
 * autorización aplicado en el backend (QA-D4).
 */
export const TEST_PRIORITY: Record<TestPriority, PriorityStyle> = {
  critica: { label: "crítica", badge: "border-red-300 bg-red-50 text-red-700" },
  alta: { label: "alta", badge: "border-amber-300 bg-amber-50 text-amber-700" },
  media: {
    label: "media",
    badge: "border-slate-300 bg-slate-50 text-slate-600",
  },
  baja: { label: "baja", badge: "border-slate-200 bg-slate-50 text-slate-500" },
};

/** Orden de mayor a menor urgencia, para ordenar listas y contadores. */
export const TEST_PRIORITY_ORDER: TestPriority[] = [
  "critica",
  "alta",
  "media",
  "baja",
];

export interface CoverageStyle {
  label: string;
  hint: string;
  badge: string;
  dot: string;
}

/**
 * Estado de una fila de la matriz.
 *
 * `uncovered` y `not_testable` NO son sinónimos y por eso no comparten color: el
 * primero es un hueco (nadie escribió el caso), el segundo es una decisión
 * respaldada por una pregunta al QA lead. Pintarlos igual haría creer que falta
 * trabajo donde lo que falta es una respuesta.
 */
export const COVERAGE_STATUS: Record<CoverageStatus, CoverageStyle> = {
  covered: {
    label: "Cubierto",
    hint: "Tiene al menos un caso de prueba.",
    badge: "bg-emerald-100 text-emerald-700 ring-emerald-200",
    dot: "bg-emerald-500",
  },
  uncovered: {
    label: "Sin cubrir",
    hint: "Ningún caso lo verifica. Bloquea si la historia es must o should; en could/wont es advertencia.",
    badge: "bg-red-100 text-red-700 ring-red-200",
    dot: "bg-red-500",
  },
  not_testable: {
    label: "No verificable",
    hint: "Declarado no verificable, con la pregunta al QA lead que lo respalda.",
    badge: "bg-amber-100 text-amber-700 ring-amber-200",
    dot: "bg-amber-500",
  },
};

/** Cuenta de casos por tipo, en el orden de presentación y sin los que valen cero. */
export function countsByKind(
  cases: { type: TestCaseType }[],
): { type: TestCaseType; count: number }[] {
  return TEST_CASE_KIND_ORDER.map((type) => ({
    type,
    count: cases.filter((c) => c.type === type).length,
  })).filter((c) => c.count > 0);
}

/**
 * Esfuerzo manual en un formato legible.
 *
 * Los minutos crudos del plan ("485 min") obligan a dividir mentalmente cada vez
 * que alguien quiere saber si el plan cabe en una tarde.
 */
export function formatMinutes(minutes: number): string {
  if (minutes < 60) return `${minutes} min`;
  const horas = Math.floor(minutes / 60);
  const resto = minutes % 60;
  return resto === 0 ? `${horas} h` : `${horas} h ${resto} min`;
}
