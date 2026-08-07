// Funciones de la API del Agente API (cliente puro de FastAPI).
//
// El archivo se llama `apis.ts` —y el router del backend cuelga de `/apis`—
// porque el prefijo global ya es `/api/v1`: `/api/v1/api/...` se leería mal en
// cada log y en cada llamada.

import type {
  ApiArtifact,
  ApiJobDetail,
  ApiJobList,
  ApiStyle,
  ApiValidationSummary,
  AvailableBdJob,
  OpenApiExport,
  SpecResult,
} from "@/lib/types/api";
import type { JobStatusGroup, QuestionStatus } from "@/lib/types/ef";

import { apiRequest } from "./client";

const JSON_HEADERS = { "content-type": "application/json" };

export const apisApi = {
  /** Genera una especificación desde un modelo de datos listo (gate 409 si no). */
  createSpec(bdJobId: string, styleOverride?: ApiStyle | null): Promise<SpecResult> {
    return apiRequest<SpecResult>("/apis/specs", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({
        bd_job_id: bdJobId,
        ...(styleOverride ? { style_override: styleOverride } : {}),
      }),
    });
  },

  availableBdJobs(limit = 20, offset = 0): Promise<{ items: AvailableBdJob[] }> {
    return apiRequest<{ items: AvailableBdJob[] }>(
      `/apis/available-bd-jobs?limit=${limit}&offset=${offset}`,
    );
  },

  getJob(jobId: string): Promise<ApiJobDetail> {
    return apiRequest<ApiJobDetail>(`/apis/jobs/${jobId}`);
  },

  getArtifact(jobId: string): Promise<ApiArtifact> {
    return apiRequest<ApiArtifact>(`/apis/jobs/${jobId}/artifact`);
  },

  /**
   * Documento OpenAPI. El YAML es el canónico (el que se validó); el JSON se
   * **re-serializa** desde él en el backend, sin llamar al modelo.
   */
  getOpenApi(jobId: string, formato: "yaml" | "json" = "yaml"): Promise<OpenApiExport> {
    return apiRequest<OpenApiExport>(
      `/apis/jobs/${jobId}/openapi?formato=${formato}`,
    );
  },

  listJobs(
    limit = 20,
    offset = 0,
    estado: JobStatusGroup = "todos",
  ): Promise<ApiJobList> {
    return apiRequest<ApiJobList>(
      `/apis/jobs?limit=${limit}&offset=${offset}&estado=${estado}`,
    );
  },

  getValidationSummary(jobId: string): Promise<ApiValidationSummary> {
    return apiRequest<ApiValidationSummary>(`/apis/jobs/${jobId}/validations`);
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
    return apiRequest(`/apis/jobs/${jobId}/validations`, {
      method: "PATCH",
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
    });
  },

  refine(jobId: string): Promise<{ job_id: string; parent_job_id: string }> {
    return apiRequest(`/apis/jobs/${jobId}/refine`, { method: "POST" });
  },
};
