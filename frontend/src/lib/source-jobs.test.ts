import { describe, expect, it } from "vitest";

import {
  blockedReasonOf,
  emptyStateFor,
  partitionSourceJobs,
  unblockHref,
  type SourceJob,
  type SourceJobPickerLabels,
} from "./source-jobs";

const LABELS: SourceJobPickerLabels = {
  singular: "diseño de arquitectura",
  plural: "diseños de arquitectura",
  jobsBasePath: "/agents/arquitectura/jobs",
  createHref: "/agents/arquitectura/new",
  createLabel: "Crear un diseño de arquitectura",
};

function job(overrides: Partial<SourceJob> & { job_id: string }): SourceJob {
  return {
    title: "Siniestros",
    status: "COMPLETED",
    ready_for_next_stage: false,
    blocking_pending: [],
    ...overrides,
  };
}

const LISTO = job({ job_id: "AR-1", ready_for_next_stage: true });
const CON_PREGUNTAS = job({ job_id: "AR-2", blocking_pending: ["Q-001", "Q-003"] });
const SIN_CONTENIDO = job({ job_id: "AR-3" });

describe("reparto de jobs de origen", () => {
  it("solo son elegibles los que tienen el semáforo en verde", () => {
    const { eligible, almostReady } = partitionSourceJobs([
      LISTO,
      CON_PREGUNTAS,
      SIN_CONTENIDO,
    ]);
    expect(eligible.map((j) => j.job_id)).toEqual(["AR-1"]);
    expect(almostReady.map((j) => j.job_id)).toEqual(["AR-2", "AR-3"]);
  });

  it("un job con avisos puede ser elegible: los avisos no son un freno", () => {
    const conAvisos = job({
      job_id: "AR-9",
      status: "COMPLETED_WITH_WARNINGS",
      ready_for_next_stage: true,
    });
    expect(partitionSourceJobs([conAvisos]).eligible).toHaveLength(1);
  });

  it("si un job no utilizable se colara, cae del lado seguro", () => {
    // El backend no debería mandarlos, pero si lo hiciera: visible, NO elegible.
    const fallido = job({ job_id: "AR-X", status: "FAILED" });
    const { eligible, almostReady } = partitionSourceJobs([fallido]);
    expect(eligible).toEqual([]);
    expect(almostReady).toHaveLength(1);
  });

  it("una lista vacía no rompe el reparto", () => {
    expect(partitionSourceJobs([])).toEqual({ eligible: [], almostReady: [] });
  });
});

describe("por qué está frenado y cómo se desbloquea", () => {
  it("distingue preguntas pendientes de contenido mínimo", () => {
    expect(blockedReasonOf(CON_PREGUNTAS)).toBe("blocking_questions");
    expect(blockedReasonOf(SIN_CONTENIDO)).toBe("minimum_content");
  });

  it("con preguntas, el enlace abre el panel de preguntas del job", () => {
    // Deep-link por hash del centro de comando: abre el panel directamente.
    expect(unblockHref(CON_PREGUNTAS, LABELS.jobsBasePath)).toBe(
      "/agents/arquitectura/jobs/AR-2#preguntas",
    );
  });

  it("sin preguntas que responder, el enlace lleva al artefacto", () => {
    expect(unblockHref(SIN_CONTENIDO, LABELS.jobsBasePath)).toBe(
      "/agents/arquitectura/jobs/AR-3",
    );
  });
});

describe("estado vacío", () => {
  it("sin ningún job, manda a crear el eslabón anterior de la cadena", () => {
    const estado = emptyStateFor([], LABELS);
    expect(estado.title).toBe("Aún no hay diseños de arquitectura listos");
    expect(estado.reason).toContain("No hay ningún diseño de arquitectura");
    expect(estado.cta).toEqual({
      href: "/agents/arquitectura/new",
      label: "Crear un diseño de arquitectura",
    });
  });

  it("con un candidato frenado por preguntas, manda a responderlas", () => {
    // Lo importante: NO propone crear otro job cuando ya hay uno a una respuesta
    // de estar listo.
    const estado = emptyStateFor([CON_PREGUNTAS], LABELS);
    expect(estado.reason).toContain("preguntas bloqueantes");
    expect(estado.cta).toEqual({
      href: "/agents/arquitectura/jobs/AR-2#preguntas",
      label: "Responder preguntas",
    });
  });

  it("con un candidato frenado por contenido mínimo, manda a revisarlo", () => {
    const estado = emptyStateFor([SIN_CONTENIDO], LABELS);
    expect(estado.reason).toContain("contenido mínimo");
    expect(estado.cta).toEqual({
      href: "/agents/arquitectura/jobs/AR-3",
      label: "Revisar",
    });
  });

  it("prefiere el candidato accionable cuando hay de los dos tipos", () => {
    // Responder preguntas es una acción concreta; "revisar" no lo es tanto.
    const estado = emptyStateFor([SIN_CONTENIDO, CON_PREGUNTAS], LABELS);
    expect(estado.cta.label).toBe("Responder preguntas");
    expect(estado.cta.href).toContain("AR-2");
  });

  it("concuerda el número: singular y plural del motivo", () => {
    expect(emptyStateFor([CON_PREGUNTAS], LABELS).reason).toContain(
      "1 diseño de arquitectura terminado, pero tiene",
    );
    const dos = emptyStateFor(
      [CON_PREGUNTAS, job({ job_id: "AR-4", blocking_pending: ["Q-002"] })],
      LABELS,
    ).reason;
    expect(dos).toContain("2 diseños de arquitectura terminados, pero tienen");
  });
});
