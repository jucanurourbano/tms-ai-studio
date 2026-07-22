import { describe, expect, it } from "vitest";

import {
  countThisMonth,
  formatCost,
  isSameMonth,
  mergeActivity,
  semaforoFor,
} from "@/lib/dashboard";
import type { JobListItem } from "@/lib/types/ef";
import type { ScrumJobListItem } from "@/lib/types/scrum";

const NOW = Date.parse("2026-07-20T12:00:00Z");

describe("semaforoFor", () => {
  it("mapea cada estado a su color", () => {
    expect(semaforoFor("COMPLETED")).toBe("green");
    expect(semaforoFor("COMPLETED_WITH_WARNINGS")).toBe("amber");
    expect(semaforoFor("NEEDS_INPUT")).toBe("amber");
    expect(semaforoFor("FAILED")).toBe("red");
    expect(semaforoFor("RUNNING")).toBe("blue");
    expect(semaforoFor("PENDING")).toBe("blue");
  });
});

describe("mergeActivity", () => {
  const ef: JobListItem[] = [
    { job_id: "ef-1", status: "COMPLETED", created_at: "2026-07-10T00:00:00Z" },
    { job_id: "ef-2", status: "FAILED", created_at: null },
  ];
  const scrum: ScrumJobListItem[] = [
    {
      job_id: "sc-1",
      status: "COMPLETED",
      created_at: "2026-07-15T00:00:00Z",
    },
  ];

  it("une ambos agentes y ordena por fecha (más reciente primero)", () => {
    const rows = mergeActivity(ef, scrum);
    expect(rows.map((r) => r.job_id)).toEqual(["sc-1", "ef-1", "ef-2"]);
    expect(rows[0].agent).toBe("scrum");
    expect(rows[0].href).toBe("/agents/scrum/jobs/sc-1");
    expect(rows[1].href).toBe("/agents/ef/jobs/ef-1");
  });

  it("coloca los ítems sin fecha al final", () => {
    const rows = mergeActivity(ef, scrum);
    expect(rows[rows.length - 1].job_id).toBe("ef-2");
  });
});

describe("isSameMonth / countThisMonth", () => {
  // Fechas a mediodía UTC para ser robustas al huso horario local (el mes se
  // evalúa en hora local, como se leen las fechas en la UI).
  it("reconoce fechas del mes actual", () => {
    expect(isSameMonth("2026-07-15T12:00:00Z", NOW)).toBe(true);
    expect(isSameMonth("2026-06-15T12:00:00Z", NOW)).toBe(false);
    expect(isSameMonth("2025-07-15T12:00:00Z", NOW)).toBe(false);
    expect(isSameMonth(null, NOW)).toBe(false);
    expect(isSameMonth("no-es-fecha", NOW)).toBe(false);
  });

  it("cuenta solo las filas del mes actual", () => {
    const rows = [
      { created_at: "2026-07-05T00:00:00Z" },
      { created_at: "2026-07-19T00:00:00Z" },
      { created_at: "2026-06-19T00:00:00Z" },
      { created_at: null },
    ];
    expect(countThisMonth(rows, NOW)).toBe(2);
  });
});

describe("formatCost", () => {
  it("formatea USD con dos decimales", () => {
    expect(formatCost(0)).toBe("$0.00");
    expect(formatCost(12.3)).toBe("$12.30");
    expect(formatCost(1204)).toBe("$1,204.00");
  });

  it("maneja valores nulos y micro-costos", () => {
    expect(formatCost(null)).toBe("$0.00");
    expect(formatCost(undefined)).toBe("$0.00");
    expect(formatCost(0.004)).toBe("<$0.01");
  });
});
