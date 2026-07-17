// Funciones de la API del Agente EF (cliente puro de FastAPI).

import type {
  AnalyzeResult,
  EFArtifact,
  JobDetail,
  JobList,
  QuestionStatus,
  RefineResult,
  ValidationSummary,
} from "@/lib/types/ef";

import { apiRequest } from "./client";

const JSON_HEADERS = { "content-type": "application/json" };

export const efApi = {
  /** Analiza texto libre (JSON). El contenido debe tener ≥ 100 caracteres. */
  analyzeText(content: string, title?: string): Promise<AnalyzeResult> {
    return apiRequest<AnalyzeResult>("/ef/analyze", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ content, title }),
    });
  },

  /** Analiza un documento (.docx/.pdf) vía multipart. */
  analyzeFile(file: File): Promise<AnalyzeResult> {
    const form = new FormData();
    form.append("file", file);
    return apiRequest<AnalyzeResult>("/ef/analyze", {
      method: "POST",
      body: form,
    });
  },

  getJob(jobId: string): Promise<JobDetail> {
    return apiRequest<JobDetail>(`/ef/jobs/${jobId}`);
  },

  getArtifact(jobId: string): Promise<EFArtifact> {
    return apiRequest<EFArtifact>(`/ef/jobs/${jobId}/artifact`);
  },

  listJobs(limit = 20, offset = 0): Promise<JobList> {
    return apiRequest<JobList>(`/ef/jobs?limit=${limit}&offset=${offset}`);
  },

  getValidationSummary(jobId: string): Promise<ValidationSummary> {
    return apiRequest<ValidationSummary>(`/ef/jobs/${jobId}/validations`);
  },

  patchValidation(
    jobId: string,
    body: {
      target_type: "question" | "assumption";
      target_id: string;
      status: QuestionStatus;
      respuesta?: string | null;
    },
  ): Promise<unknown> {
    return apiRequest(`/ef/jobs/${jobId}/validations`, {
      method: "PATCH",
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
    });
  },

  refine(jobId: string): Promise<RefineResult> {
    return apiRequest<RefineResult>(`/ef/jobs/${jobId}/refine`, {
      method: "POST",
    });
  },
};
