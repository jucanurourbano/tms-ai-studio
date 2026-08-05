// Funciones de la API del Agente BD (cliente puro de FastAPI).

import type { JobStatusGroup, QuestionStatus } from "@/lib/types/ef";
import type {
  AvailableArchitectureJob,
  DatabaseArtifact,
  DbEngine,
  DbJobDetail,
  DbJobList,
  DbValidationSummary,
  DdlExport,
  ModelResult,
} from "@/lib/types/bd";

import { apiRequest } from "./client";

const JSON_HEADERS = { "content-type": "application/json" };

export const bdApi = {
  /** Genera un modelo desde un diseño de arquitectura listo (gate 409 si no). */
  createModel(
    architectureJobId: string,
    engineOverride?: DbEngine | null,
  ): Promise<ModelResult> {
    return apiRequest<ModelResult>("/bd/models", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({
        architecture_job_id: architectureJobId,
        ...(engineOverride ? { engine_override: engineOverride } : {}),
      }),
    });
  },

  availableArchitectureJobs(
    limit = 20,
    offset = 0,
  ): Promise<{ items: AvailableArchitectureJob[] }> {
    return apiRequest<{ items: AvailableArchitectureJob[] }>(
      `/bd/available-architecture-jobs?limit=${limit}&offset=${offset}`,
    );
  },

  getJob(jobId: string): Promise<DbJobDetail> {
    return apiRequest<DbJobDetail>(`/bd/jobs/${jobId}`);
  },

  getArtifact(jobId: string): Promise<DatabaseArtifact> {
    return apiRequest<DatabaseArtifact>(`/bd/jobs/${jobId}/artifact`);
  },

  /**
   * DDL del modelo. Con `engine` distinto al del artefacto, el backend lo
   * **re-renderiza sin llamar al modelo** (el artefacto guarda el tipo lógico de
   * cada columna) y sin mutar nada.
   */
  getDdl(jobId: string, engine?: DbEngine | null): Promise<DdlExport> {
    const query = engine ? `?engine=${engine}` : "";
    return apiRequest<DdlExport>(`/bd/jobs/${jobId}/ddl${query}`);
  },

  listJobs(
    limit = 20,
    offset = 0,
    estado: JobStatusGroup = "todos",
  ): Promise<DbJobList> {
    return apiRequest<DbJobList>(
      `/bd/jobs?limit=${limit}&offset=${offset}&estado=${estado}`,
    );
  },

  getValidationSummary(jobId: string): Promise<DbValidationSummary> {
    return apiRequest<DbValidationSummary>(`/bd/jobs/${jobId}/validations`);
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
    return apiRequest(`/bd/jobs/${jobId}/validations`, {
      method: "PATCH",
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
    });
  },

  refine(jobId: string): Promise<{ job_id: string; parent_job_id: string }> {
    return apiRequest(`/bd/jobs/${jobId}/refine`, { method: "POST" });
  },
};
