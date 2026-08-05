import { describe, expect, it } from "vitest";

import { draftFor, syncDraft, type ValidationDraft } from "./validation-draft";

/** Aplica la sincronización como lo hace el componente en cada render. */
function render(
  draft: ValidationDraft,
  targetId: string,
  respuesta?: string | null,
): ValidationDraft {
  return syncDraft(draft, targetId, respuesta) ?? draft;
}

describe("aislamiento del borrador por pregunta", () => {
  it("REGRESIÓN: el texto de una pregunta no viaja a la siguiente", () => {
    // El bug real: se respondió Q-004 y, al avanzar, Q-005 mostraba el mismo
    // texto; al confirmar, Q-005 quedó guardada con la respuesta de Q-004.
    let draft = draftFor("Q-004", null);
    draft = { ...draft, text: "Si RRHH no valida en 2 días hábiles…" };

    // Avanza a Q-005, que está pendiente: la caja debe quedar VACÍA.
    draft = render(draft, "Q-005", null);
    expect(draft.targetId).toBe("Q-005");
    expect(draft.text).toBe("");
  });

  it("al volver a una pregunta respondida, muestra SU respuesta guardada", () => {
    let draft = draftFor("Q-005", null);
    // Vuelve a Q-004, que ya tiene respuesta.
    draft = render(draft, "Q-004", "Respuesta de Q-004");
    expect(draft.text).toBe("Respuesta de Q-004");
  });

  it("recorrido completo: responder, avanzar y volver", () => {
    // 1) Q-001 pendiente: caja vacía.
    let draft = draftFor("Q-001", null);
    expect(draft.text).toBe("");

    // 2) Se escribe y se guarda: el padre recarga y ahora llega `respuesta`.
    draft = { ...draft, text: "Vacaciones se aprueban por el jefe directo." };
    draft = render(draft, "Q-001", "Vacaciones se aprueban por el jefe directo.");
    expect(draft.text).toBe("Vacaciones se aprueban por el jefe directo.");

    // 3) Avance automático a Q-002, pendiente: vacía.
    draft = render(draft, "Q-002", null);
    expect(draft.text).toBe("");

    // 4) Se vuelve atrás a Q-001: su respuesta, no la de nadie más.
    draft = render(draft, "Q-001", "Vacaciones se aprueban por el jefe directo.");
    expect(draft.text).toBe("Vacaciones se aprueban por el jefe directo.");
  });

  it("no pisa lo que se está escribiendo en re-renders del padre", () => {
    // El padre se re-renderiza en cada recarga del resumen de validaciones; si
    // eso reiniciara la caja, escribir sería imposible.
    let draft = draftFor("Q-001", null);
    draft = { ...draft, text: "a medio escri" };
    draft = render(draft, "Q-001", null);
    draft = render(draft, "Q-001", null);
    expect(draft.text).toBe("a medio escri");
  });

  it("si la respuesta guardada cambia por fuera, la caja se pone al día", () => {
    // Caso "volver a pendiente": el servidor borra la respuesta y la caja debe
    // quedar vacía, no conservar el texto anterior.
    let draft = draftFor("Q-004", "Respuesta vieja");
    expect(draft.text).toBe("Respuesta vieja");
    draft = render(draft, "Q-004", null);
    expect(draft.text).toBe("");
  });

  it("dos preguntas con la misma respuesta guardada siguen siendo distintas", () => {
    // Es el estado corrupto que dejó el bug: si el aislamiento dependiera solo
    // del texto, volver de una a otra no reiniciaría nada.
    let draft = draftFor("Q-004", "Mismo texto");
    draft = { ...draft, text: "Editado a mano" };
    draft = render(draft, "Q-005", "Mismo texto");
    expect(draft.targetId).toBe("Q-005");
    expect(draft.text).toBe("Mismo texto");
  });

  it("`syncDraft` devuelve null cuando no hay nada que reiniciar", () => {
    const draft = draftFor("Q-001", "x");
    expect(syncDraft(draft, "Q-001", "x")).toBeNull();
    expect(syncDraft(draft, "Q-002", "x")).not.toBeNull();
    expect(syncDraft(draft, "Q-001", "y")).not.toBeNull();
  });

  it("trata null y cadena vacía como lo mismo: no reinicia de más", () => {
    const draft = draftFor("Q-001", null);
    expect(syncDraft(draft, "Q-001", "")).toBeNull();
  });
});
