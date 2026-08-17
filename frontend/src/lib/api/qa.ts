// Funciones de la API del Agente QA (cliente puro de FastAPI).

import type {
  AvailableScrumJob,
  CompatibleApiJob,
  QaArtifact,
  QaCsvExport,
  QaJobDetail,
  QaJobList,
  QaValidationSummary,
  TestPlanResult,
} from "@/lib/types/qa";
import type { JobStatusGroup, QuestionStatus } from "@/lib/types/ef";

import { apiRequest } from "./client";

const JSON_HEADERS = { "content-type": "application/json" };

export interface CreateTestPlanOptions {
  /** Contrato de API contra el que diseñar los casos de autorización (QA-D1). */
  apiJobId?: string | null;
  coverageThreshold?: number | null;
  maxCasesPerCriterion?: number | null;
  manualCapacityMinutes?: number | null;
}

export const qaApi = {
  /** Genera un plan de pruebas desde un plan Scrum listo (gate 409 si no). */
  createPlan(
    scrumJobId: string,
    options: CreateTestPlanOptions = {},
  ): Promise<TestPlanResult> {
    const body: Record<string, unknown> = { scrum_job_id: scrumJobId };
    if (options.apiJobId) body.api_job_id = options.apiJobId;
    if (options.coverageThreshold != null)
      body.coverage_threshold = options.coverageThreshold;
    if (options.maxCasesPerCriterion != null)
      body.max_cases_per_criterion = options.maxCasesPerCriterion;
    if (options.manualCapacityMinutes != null)
      body.manual_capacity_minutes = options.manualCapacityMinutes;
    return apiRequest<TestPlanResult>("/qa/plans", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
    });
  },

  availableScrumJobs(
    limit = 20,
    offset = 0,
  ): Promise<{ items: AvailableScrumJob[] }> {
    return apiRequest<{ items: AvailableScrumJob[] }>(
      `/qa/available-scrum-jobs?limit=${limit}&offset=${offset}`,
    );
  },

  /**
   * Contratos de API de la cadena de ese plan. El descubrimiento es una ayuda:
   * la elección es del QA lead, porque "el más reciente" adivinaría contra qué
   * contrato quiere probar.
   */
  compatibleApiJobs(
    scrumJobId: string,
  ): Promise<{ items: CompatibleApiJob[] }> {
    return apiRequest<{ items: CompatibleApiJob[] }>(
      `/qa/compatible-api-jobs?scrum_job_id=${encodeURIComponent(scrumJobId)}`,
    );
  },

  getJob(jobId: string): Promise<QaJobDetail> {
    return apiRequest<QaJobDetail>(`/qa/jobs/${jobId}`);
  },

  getArtifact(jobId: string): Promise<QaArtifact> {
    return apiRequest<QaArtifact>(`/qa/jobs/${jobId}/artifact`);
  },

  /** CSV de los casos o de la matriz, con BOM y `;` para que Excel lo abra. */
  exportCsv(
    jobId: string,
    cual: "casos" | "matriz" = "casos",
  ): Promise<QaCsvExport> {
    return apiRequest<QaCsvExport>(`/qa/jobs/${jobId}/export?cual=${cual}`);
  },

  listJobs(
    limit = 20,
    offset = 0,
    estado: JobStatusGroup = "todos",
  ): Promise<QaJobList> {
    return apiRequest<QaJobList>(
      `/qa/jobs?limit=${limit}&offset=${offset}&estado=${estado}`,
    );
  },

  getValidationSummary(jobId: string): Promise<QaValidationSummary> {
    return apiRequest<QaValidationSummary>(`/qa/jobs/${jobId}/validations`);
  },

  patchValidation(
    jobId: string,
    body: {
      target_type: "question";
      target_id: string;
      status: QuestionStatus;
      respuesta?: string | null;
    },
  ): Promise<unknown> {
    return apiRequest(`/qa/jobs/${jobId}/validations`, {
      method: "PATCH",
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
    });
  },

  refine(jobId: string): Promise<{ job_id: string; parent_job_id: string }> {
    return apiRequest(`/qa/jobs/${jobId}/refine`, { method: "POST" });
  },
};
