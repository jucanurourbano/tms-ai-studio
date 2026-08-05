import { describe, expect, it } from "vitest";

import { initialQuestionIndex, nextPendingIndex } from "./focused-questions";
import type { QuestionStatus } from "./types/ef";

const PREGUNTAS = [
  { id: "Q-001" },
  { id: "Q-002" },
  { id: "Q-003" },
  { id: "Q-004" },
];

/** Construye un `statusOf` desde un mapa id → estado (lo ausente es pendiente). */
function estados(mapa: Record<string, QuestionStatus>) {
  return (id: string): QuestionStatus => mapa[id] ?? "pendiente";
}

describe("avance automático al responder", () => {
  it("salta a la siguiente pendiente, no a la siguiente por orden", () => {
    // Q-002 ya está respondida: responder Q-001 debe llevar a Q-003.
    const statusOf = estados({ "Q-002": "confirmado" });
    expect(nextPendingIndex(PREGUNTAS, statusOf, 0)).toBe(2);
  });

  it("da la vuelta si las pendientes quedaron atrás", () => {
    const statusOf = estados({
      "Q-002": "confirmado",
      "Q-003": "corregido",
      "Q-004": "confirmado",
    });
    // Desde la última, la única pendiente es Q-001 (índice 0).
    expect(nextPendingIndex(PREGUNTAS, statusOf, 3)).toBe(0);
  });

  it("NO vuelve a la que se acaba de responder aunque figure pendiente", () => {
    // Este es el caso que importa: el resumen se recarga en segundo plano, así
    // que en el instante de decidir, la recién respondida aún dice "pendiente".
    // Sin excluir `from`, responder la última "avanzaba" a ella misma y el flujo
    // nunca llegaba al cierre.
    const todasPendientes = estados({});
    expect(nextPendingIndex([{ id: "Q-001" }], todasPendientes, 0)).toBeNull();

    const soloQueda = estados({ "Q-001": "confirmado", "Q-002": "confirmado" });
    expect(
      nextPendingIndex([{ id: "Q-001" }, { id: "Q-002" }], soloQueda, 1),
    ).toBeNull();
  });

  it("devuelve null cuando no queda ninguna pendiente: hay que cerrar", () => {
    const statusOf = estados({
      "Q-001": "confirmado",
      "Q-002": "confirmado",
      "Q-003": "corregido",
      "Q-004": "confirmado",
    });
    expect(nextPendingIndex(PREGUNTAS, statusOf, 0)).toBeNull();
  });

  it("una lista vacía no rompe la regla", () => {
    expect(nextPendingIndex([], estados({}), 0)).toBeNull();
  });

  it("con varias pendientes por delante, elige la más cercana", () => {
    const statusOf = estados({ "Q-001": "confirmado" });
    expect(nextPendingIndex(PREGUNTAS, statusOf, 1)).toBe(2);
  });
});

describe("pregunta con la que se abre el flujo", () => {
  it("arranca en la primera pendiente", () => {
    const statusOf = estados({ "Q-001": "confirmado", "Q-002": "corregido" });
    expect(initialQuestionIndex(PREGUNTAS, statusOf)).toBe(2);
  });

  it("con todo respondido arranca en la primera: abrirlo no es un error", () => {
    const statusOf = estados({
      "Q-001": "confirmado",
      "Q-002": "confirmado",
      "Q-003": "confirmado",
      "Q-004": "confirmado",
    });
    expect(initialQuestionIndex(PREGUNTAS, statusOf)).toBe(0);
  });

  it("sin preguntas devuelve 0 y el componente muestra su vacío", () => {
    expect(initialQuestionIndex([], estados({}))).toBe(0);
  });
});
