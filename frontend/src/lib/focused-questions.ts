// Regla de avance del modo "una a una" del panel de preguntas.
//
// Vive fuera del componente para poder testearse sin montar la interfaz, igual
// que las reglas del selector de origen. Es una regla pequeña con un detalle que
// se escapa fácil, y por eso merece test propio: el resumen de validaciones se
// recarga **de forma asíncrona** después de guardar, así que en el instante en que
// hay que decidir a dónde saltar, la pregunta recién respondida todavía figura
// como pendiente.

import type { QuestionStatus } from "@/lib/types/ef";

/** Lo mínimo que necesita la regla de cada pregunta. */
export interface AdvanceableQuestion {
  id: string;
}

/**
 * Índice de la siguiente pregunta **pendiente**, o `null` si no queda ninguna.
 *
 * Busca hacia adelante desde `from` y, si no encuentra nada, da la vuelta: no
 * tiene sentido obligar a recorrer las ya respondidas para llegar a la que quedó
 * atrás. `from` se excluye **siempre**, también al dar la vuelta, porque acaba de
 * responderse y su estado aún no ha llegado del servidor.
 */
export function nextPendingIndex(
  questions: readonly AdvanceableQuestion[],
  statusOf: (id: string) => QuestionStatus,
  from: number,
): number | null {
  const pendiente = (q: AdvanceableQuestion, i: number) =>
    i !== from && statusOf(q.id) === "pendiente";
  const adelante = questions.findIndex((q, i) => i > from && pendiente(q, i));
  if (adelante !== -1) return adelante;
  const dandoLaVuelta = questions.findIndex(pendiente);
  return dandoLaVuelta === -1 ? null : dandoLaVuelta;
}

/**
 * Índice con el que abrir el flujo: la primera pendiente, o la primera pregunta
 * si están todas resueltas (abrir un artefacto terminado no es un error).
 */
export function initialQuestionIndex(
  questions: readonly AdvanceableQuestion[],
  statusOf: (id: string) => QuestionStatus,
): number {
  const i = questions.findIndex((q) => statusOf(q.id) === "pendiente");
  return i === -1 ? 0 : i;
}
