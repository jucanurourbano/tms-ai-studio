// Funciones de la API del Agente Arquitectura (cliente puro de FastAPI).

import type { QuestionStatus } from "@/lib/types/ef";
import type {
  ArchitectureArtifact,
  ArchJobDetail,
  ArchJobList,
  ArchValidationSummary,
  AvailableScrumJob,
  DesignResult,
} from "@/lib/types/arquitectura";

import { apiRequest } from "./client";

const JSON_HEADERS = { "content-type": "application/json" };

export const arquitecturaApi = {
  /** Genera un diseño a partir de un plan Scrum listo (gate 409 si no lo está). */
  createDesign(scrumJobId: string): Promise<DesignResult> {
    return apiRequest<DesignResult>("/arquitectura/designs", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ scrum_job_id: scrumJobId }),
    });
  },

  availableScrumJobs(
    limit = 20,
    offset = 0,
  ): Promise<{ items: AvailableScrumJob[] }> {
    return apiRequest<{ items: AvailableScrumJob[] }>(
      `/arquitectura/available-scrum-jobs?limit=${limit}&offset=${offset}`,
    );
  },

  getJob(jobId: string): Promise<ArchJobDetail> {
    return apiRequest<ArchJobDetail>(`/arquitectura/jobs/${jobId}`);
  },

  getArtifact(jobId: string): Promise<ArchitectureArtifact> {
    return apiRequest<ArchitectureArtifact>(
      `/arquitectura/jobs/${jobId}/artifact`,
    );
  },

  listJobs(limit = 20, offset = 0): Promise<ArchJobList> {
    return apiRequest<ArchJobList>(
      `/arquitectura/jobs?limit=${limit}&offset=${offset}`,
    );
  },

  getValidationSummary(jobId: string): Promise<ArchValidationSummary> {
    return apiRequest<ArchValidationSummary>(
      `/arquitectura/jobs/${jobId}/validations`,
    );
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
    return apiRequest(`/arquitectura/jobs/${jobId}/validations`, {
      method: "PATCH",
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
    });
  },

  refine(jobId: string): Promise<{ job_id: string; parent_job_id: string }> {
    return apiRequest(`/arquitectura/jobs/${jobId}/refine`, { method: "POST" });
  },
};
