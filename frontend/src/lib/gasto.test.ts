import { describe, expect, it } from "vitest";

import {
  USAGE_SOURCE_STYLE,
  formatPct,
  formatUsd,
  isUnattributed,
  progressTone,
  progressWidth,
  stageLabel,
} from "./gasto";
import type { TotalUsageSource } from "./types/gasto";

describe("formatUsd", () => {
  it("lee los totales en céntimos", () => {
    expect(formatUsd("22.410000")).toBe("$22.41");
  });

  it("no aplasta a cero una fila pequeña del desglose", () => {
    // Es el caso que importa: `by_stage` tiene que enseñar el antes/después de
    // recortar un nodo, y a dos decimales 0,003 se leería "$0.00".
    expect(formatUsd("0.003400", 4)).toBe("$0.0034");
    expect(formatUsd("0.003400")).toBe("$0.00");
  });

  it("devuelve un guion ante un importe que no es un número", () => {
    expect(formatUsd("")).toBe("—");
  });
});

describe("formatPct", () => {
  it("dice que el porcentaje NO existe cuando el tope es 0", () => {
    // `0%` diría "no has empezado" justo cuando cualquier gasto ya lo cruzó.
    expect(formatPct(null)).toBe("—");
  });

  it("formatea el avance", () => {
    expect(formatPct(74.7)).toBe("74.7%");
  });
});

describe("USAGE_SOURCE_STYLE", () => {
  const todas: TotalUsageSource[] = ["real", "mixto", "estimado", "sin_datos"];

  it("cubre las cuatro clases de total del backend", () => {
    // Si el backend amplía el vocabulario, este test obliga a escribir aquí qué
    // significa la clase nueva en vez de dejarla sin etiqueta en pantalla.
    expect(Object.keys(USAGE_SOURCE_STYLE).sort()).toEqual([...todas].sort());
  });

  it("cada clase explica qué implica para quien lee la cifra", () => {
    for (const clase of todas) {
      expect(USAGE_SOURCE_STYLE[clase].hint.length).toBeGreaterThan(20);
    }
  });

  it("distingue estimado de mixto", () => {
    expect(USAGE_SOURCE_STYLE.estimado.label).not.toBe(
      USAGE_SOURCE_STYLE.mixto.label,
    );
  });
});

describe("stageLabel", () => {
  it("nombra el gasto que ningún nodo reclama", () => {
    expect(stageLabel(null)).toBe("Sin nodo atribuido");
    expect(isUnattributed(null)).toBe(true);
  });

  it("deja el nodo tal cual cuando lo hay", () => {
    expect(stageLabel("EDGE_CASES")).toBe("EDGE_CASES");
    expect(isUnattributed("EDGE_CASES")).toBe(false);
  });
});

describe("progreso contra el tope", () => {
  it("avisa antes de agotar el margen para reaccionar", () => {
    expect(progressTone(40)).toBe("bg-emerald-500");
    expect(progressTone(85)).toBe("bg-amber-500");
    expect(progressTone(120)).toBe("bg-red-500");
  });

  it("pasarse del tope no desborda la barra", () => {
    expect(progressWidth(250)).toBe("100%");
    expect(progressWidth(null)).toBe("0%");
    expect(progressWidth(33.3)).toBe("33.3%");
  });
});
