// Funciones de la API del Inventario de Sistemas (cliente puro de FastAPI).

import type {
  AssetType,
  AssetValidationStatus,
  DdlImportReport,
  IntrospectionSource,
  InventoryAsset,
  InventorySystem,
  KnowledgeExtractionReport,
  StackEntry,
  SystemKind,
  SystemStatus,
} from "@/lib/types/inventario";

import { apiRequest } from "./client";

const JSON_HEADERS = { "content-type": "application/json" };

export interface CreateSystemInput {
  name: string;
  kind: SystemKind;
  description?: string | null;
  status?: SystemStatus;
  stack?: StackEntry[] | null;
}

export type UpdateSystemInput = Partial<CreateSystemInput>;

export const inventarioApi = {
  listSystems(kind?: SystemKind): Promise<{ items: InventorySystem[] }> {
    const query = kind ? `?kind=${kind}` : "";
    return apiRequest<{ items: InventorySystem[] }>(
      `/inventario/systems${query}`,
    );
  },

  getSystem(systemId: string): Promise<InventorySystem> {
    return apiRequest<InventorySystem>(`/inventario/systems/${systemId}`);
  },

  createSystem(input: CreateSystemInput): Promise<InventorySystem> {
    return apiRequest<InventorySystem>("/inventario/systems", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(input),
    });
  },

  updateSystem(
    systemId: string,
    input: UpdateSystemInput,
  ): Promise<InventorySystem> {
    return apiRequest<InventorySystem>(`/inventario/systems/${systemId}`, {
      method: "PATCH",
      headers: JSON_HEADERS,
      body: JSON.stringify(input),
    });
  },

  deleteSystem(systemId: string): Promise<{ system_id: string }> {
    return apiRequest<{ system_id: string }>(`/inventario/systems/${systemId}`, {
      method: "DELETE",
    });
  },

  listAssets(
    systemId: string,
    assetType?: AssetType,
  ): Promise<{ items: InventoryAsset[] }> {
    const query = assetType ? `?asset_type=${assetType}` : "";
    return apiRequest<{ items: InventoryAsset[] }>(
      `/inventario/systems/${systemId}/assets${query}`,
    );
  },

  getAsset(assetId: string): Promise<InventoryAsset> {
    return apiRequest<InventoryAsset>(`/inventario/assets/${assetId}`);
  },

  listVersions(assetId: string): Promise<{ items: InventoryAsset[] }> {
    return apiRequest<{ items: InventoryAsset[] }>(
      `/inventario/assets/${assetId}/versions`,
    );
  },

  createAsset(
    systemId: string,
    input: {
      asset_type: AssetType;
      name: string;
      content: Record<string, unknown>;
      description?: string | null;
      origin?: string;
      origin_ref?: string | null;
    },
  ): Promise<InventoryAsset> {
    return apiRequest<InventoryAsset>(
      `/inventario/systems/${systemId}/assets`,
      { method: "POST", headers: JSON_HEADERS, body: JSON.stringify(input) },
    );
  },

  setAssetStatus(
    assetId: string,
    status: AssetValidationStatus,
  ): Promise<InventoryAsset> {
    return apiRequest<InventoryAsset>(`/inventario/assets/${assetId}/status`, {
      method: "PATCH",
      headers: JSON_HEADERS,
      body: JSON.stringify({ validation_status: status }),
    });
  },

  deleteAsset(assetId: string): Promise<{ asset_id: string }> {
    return apiRequest<{ asset_id: string }>(`/inventario/assets/${assetId}`, {
      method: "DELETE",
    });
  },

  /** Sube un dump DDL. `import_report` dice qué se leyó y qué NO. */
  uploadDdl(
    systemId: string,
    file: File,
    name = "core",
  ): Promise<InventoryAsset & { import_report: DdlImportReport }> {
    const form = new FormData();
    form.append("file", file);
    // Sin `content-type`: el navegador pone el boundary del multipart.
    return apiRequest<InventoryAsset & { import_report: DdlImportReport }>(
      `/inventario/systems/${systemId}/assets/ddl?name=${encodeURIComponent(name)}`,
      { method: "POST", body: form },
    );
  },

  /** Sube un documento y extrae su conocimiento (docx/pdf/txt/md). */
  uploadDocument(
    systemId: string,
    file: File,
  ): Promise<{
    assets: InventoryAsset[];
    extraction_report: KnowledgeExtractionReport;
  }> {
    const form = new FormData();
    form.append("file", file);
    return apiRequest<{
      assets: InventoryAsset[];
      extraction_report: KnowledgeExtractionReport;
    }>(`/inventario/systems/${systemId}/assets/document`, {
      method: "POST",
      body: form,
    });
  },

  /** Orígenes de introspección autorizados (solo admin; nunca trae credenciales). */
  introspectionSources(): Promise<{ items: IntrospectionSource[] }> {
    return apiRequest<{ items: IntrospectionSource[] }>(
      "/inventario/introspection/sources",
    );
  },

  introspect(
    systemId: string,
    alias: string,
    schema = "public",
    name = "core",
  ): Promise<InventoryAsset> {
    return apiRequest<InventoryAsset>(
      `/inventario/systems/${systemId}/assets/introspect`,
      {
        method: "POST",
        headers: JSON_HEADERS,
        body: JSON.stringify({ alias, schema, name }),
      },
    );
  },

  /** Promueve un artefacto terminado de BD o API al inventario (INV6). */
  promote(
    systemId: string,
    jobId: string,
    assetName?: string,
  ): Promise<InventoryAsset> {
    return apiRequest<InventoryAsset>(
      `/inventario/systems/${systemId}/promote`,
      {
        method: "POST",
        headers: JSON_HEADERS,
        body: JSON.stringify({
          job_id: jobId,
          ...(assetName ? { asset_name: assetName } : {}),
        }),
      },
    );
  },
};
