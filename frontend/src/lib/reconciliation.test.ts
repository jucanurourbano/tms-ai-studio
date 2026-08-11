import { describe, expect, it } from "vitest";

import {
  RECONCILIATION_ORDER,
  RECONCILIATION_STYLE,
  styleOf,
  summaryChips,
  summaryHeadline,
  type ReconciliationStatus,
  type ReconciliationSummary,
} from "./reconciliation";

const ESTADOS: ReconciliationStatus[] = ["reuse", "extend", "new", "conflict"];

function resumen(
  parcial: Partial<ReconciliationSummary> = {},
): ReconciliationSummary {
  return {
    system_id: "sys-1",
    system_name: "TMS Moderno",
    counts: {},
    blocking: 0,
    reconciled: 0,
    total: 0,
    performed: true,
    reason: "",
    ...parcial,
  };
}

describe("vocabulario visual", () => {
  it("cubre los cuatro estados con etiqueta, explicación y color", () => {
    for (const estado of ESTADOS) {
      const estilo = styleOf(estado);
      expect(estilo.label).toBeTruthy();
      // La explicación no es opcional: un color sin significado obligaría a
      // fiarse de una decisión automática sobre un sistema de producción.
      expect(estilo.hint).toBeTruthy();
      expect(estilo.badge).toBeTruthy();
      expect(estilo.dot).toBeTruthy();
    }
  });

  it("usa los colores acordados y no los reparte al azar", () => {
    expect(RECONCILIATION_STYLE.reuse.badge).toContain("emerald"); // verde
    expect(RECONCILIATION_STYLE.extend.badge).toContain("blue"); // azul
    expect(RECONCILIATION_STYLE.new.badge).toContain("violet"); // violeta
    expect(RECONCILIATION_STYLE.conflict.badge).toContain("red"); // rojo
  });

  it("presenta primero lo que reclama atención", () => {
    expect(RECONCILIATION_ORDER[0]).toBe("conflict");
    expect(new Set(RECONCILIATION_ORDER)).toEqual(new Set(ESTADOS));
  });
});

describe("titular del resumen", () => {
  it("distingue «no se reconcilió» de «no había nada»", () => {
    // Es la confusión cara: leer un diseño como validado contra el inventario
    // cuando nadie lo comparó con nada.
    const noEjecutada = summaryHeadline(
      resumen({ performed: false, reason: "No hay sistema destino." }),
    );
    expect(noEjecutada).toBe("No hay sistema destino.");

    const sinElementos = summaryHeadline(resumen({ performed: true, total: 0 }));
    expect(sinElementos).toContain("Sin elementos que reconciliar");
    expect(sinElementos).toContain("TMS Moderno");
  });

  it("sin resumen alguno, lo dice en vez de callar", () => {
    expect(summaryHeadline(null)).toContain("No se reconcilió");
  });

  it("cuenta lo reutilizado sobre el total", () => {
    const texto = summaryHeadline(
      resumen({ total: 10, reconciled: 7, blocking: 0 }),
    );
    expect(texto).toContain("7 de 10");
    expect(texto).toContain("TMS Moderno");
  });

  it("destaca lo que queda sin confirmar", () => {
    const texto = summaryHeadline(
      resumen({ total: 10, reconciled: 7, blocking: 2 }),
    );
    expect(texto).toContain("2 sin confirmar");
  });
});

describe("chips del resumen", () => {
  it("omite los estados en cero para no llenar la franja de ruido", () => {
    const chips = summaryChips(
      resumen({ counts: { reuse: 3, new: 2, extend: 0, conflict: 0 } }),
    );
    expect(chips.map((c) => c.status)).toEqual(["reuse", "new"]);
  });

  it("pone el conflicto delante aunque haya menos", () => {
    const chips = summaryChips(
      resumen({ counts: { reuse: 9, conflict: 1 } }),
    );
    expect(chips[0]).toEqual({ status: "conflict", count: 1 });
  });

  it("no muestra chips si la fase no se ejecutó", () => {
    expect(summaryChips(resumen({ performed: false, counts: { new: 3 } }))).toEqual(
      [],
    );
    expect(summaryChips(null)).toEqual([]);
  });
});
