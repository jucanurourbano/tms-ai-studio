// Funciones de la API del Agente Scrum (cliente puro de FastAPI).

import type { QuestionStatus } from "@/lib/types/ef";
import type {
  AvailableEfJob,
  PlanResult,
  ScrumArtifact,
  ScrumExport,
  ScrumJobDetail,
  ScrumJobList,
  ScrumValidationSummary,
} from "@/lib/types/scrum";

import { apiRequest } from "./client";

const JSON_HEADERS = { "content-type": "application/json" };

export const scrumApi = {
  /** Genera un plan ágil a partir de un job EF listo (gate 4xx si no lo está). */
  createPlan(efJobId: string, capacityPoints?: number): Promise<PlanResult> {
    return apiRequest<PlanResult>("/scrum/plans", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({
        ef_job_id: efJobId,
        capacity_points: capacityPoints ?? null,
      }),
    });
  },

  availableEfJobs(limit = 20, offset = 0): Promise<{ items: AvailableEfJob[] }> {
    return apiRequest<{ items: AvailableEfJob[] }>(
      `/scrum/available-ef-jobs?limit=${limit}&offset=${offset}`,
    );
  },

  getJob(jobId: string): Promise<ScrumJobDetail> {
    return apiRequest<ScrumJobDetail>(`/scrum/jobs/${jobId}`);
  },

  getArtifact(jobId: string): Promise<ScrumArtifact> {
    return apiRequest<ScrumArtifact>(`/scrum/jobs/${jobId}/artifact`);
  },

  listJobs(limit = 20, offset = 0): Promise<ScrumJobList> {
    return apiRequest<ScrumJobList>(`/scrum/jobs?limit=${limit}&offset=${offset}`);
  },

  getValidationSummary(jobId: string): Promise<ScrumValidationSummary> {
    return apiRequest<ScrumValidationSummary>(`/scrum/jobs/${jobId}/validations`);
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
    return apiRequest(`/scrum/jobs/${jobId}/validations`, {
      method: "PATCH",
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
    });
  },

  refine(jobId: string): Promise<{ job_id: string; parent_job_id: string }> {
    return apiRequest(`/scrum/jobs/${jobId}/refine`, { method: "POST" });
  },

  export(jobId: string, format: "csv" | "json"): Promise<ScrumExport> {
    return apiRequest<ScrumExport>(
      `/scrum/jobs/${jobId}/export?format=${format}`,
    );
  },
};
