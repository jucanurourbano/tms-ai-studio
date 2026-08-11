// Tipos del Inventario de Sistemas (espejo de los esquemas del backend).

export type SystemKind = "destino" | "legado" | "externo";

export type SystemStatus =
  | "en_construccion"
  | "activo"
  | "en_migracion"
  | "retirado";

export type AssetType = "db_schema" | "module" | "api" | "document";

export type AssetOrigin =
  | "ddl_dump"
  | "introspection"
  | "document"
  | "manual"
  | "isdf";

export type AssetValidationStatus = "importado" | "validado";

export interface StackEntry {
  layer: string;
  technology: string;
  version?: string | null;
}

export interface InventorySystem {
  id: string;
  name: string;
  description: string | null;
  kind: SystemKind;
  status: SystemStatus;
  stack: StackEntry[];
  created_at: string | null;
  updated_at: string | null;
  /** Conteo de activos VIGENTES por tipo (lo calcula el backend). */
  asset_counts?: Partial<Record<AssetType, number>>;
  assets?: InventoryAsset[];
}

/** Resumen barato del contenido, para no tener que abrir el activo. */
export interface AssetSummary {
  tables?: number;
  columns?: number;
  endpoints?: number;
  functionalities?: number;
  entities?: number;
  keys?: number;
}

export interface InventoryAsset {
  id: string;
  system_id: string;
  asset_type: AssetType;
  name: string;
  description: string | null;
  origin: AssetOrigin;
  origin_ref: string | null;
  version: number;
  validation_status: AssetValidationStatus;
  created_at: string | null;
  updated_at: string | null;
  /** Solo al abrir el activo (los listados lo omiten a propósito). */
  content?: DbSchemaContent | Record<string, unknown>;
  /** Solo en los listados. */
  summary?: AssetSummary;
  /** Solo al cargar un DDL: qué se leyó y qué no. */
  import_report?: DdlImportReport;
  /** Solo al promover: qué cambió respecto de la versión anterior. */
  changes?: { added: string[]; updated: string[]; kept: string[] };
}

// --- Contenido de un activo `db_schema` -------------------------------------

export interface InventoryColumn {
  name: string;
  type: string;
  logical_type?: string | null;
  nullable: boolean;
  default?: string | null;
  primary_key: boolean;
  comment?: string | null;
}

export interface InventoryForeignKey {
  name?: string | null;
  columns: string[];
  referenced_table: string;
  referenced_columns: string[];
  on_delete?: string | null;
}

export interface InventoryConstraint {
  kind: "unique" | "check";
  name?: string | null;
  columns: string[];
  expression?: string | null;
}

export interface InventoryIndex {
  name?: string | null;
  columns: string[];
  unique: boolean;
}

export interface InventoryTable {
  name: string;
  schema_name?: string | null;
  comment?: string | null;
  columns: InventoryColumn[];
  primary_key: string[];
  foreign_keys: InventoryForeignKey[];
  constraints: InventoryConstraint[];
  indexes: InventoryIndex[];
}

export interface DbSchemaContent {
  engine?: string | null;
  tables: InventoryTable[];
}

// --- Informes ---------------------------------------------------------------

export interface DdlImportIssue {
  code: string;
  message: string;
  line: number | null;
}

export interface DdlImportReport {
  tables: number;
  columns: number;
  parsed_statements: number;
  ignored_statements: number;
  errors: DdlImportIssue[];
  warnings: DdlImportIssue[];
}

export interface KnowledgeExtractionReport {
  fragments: number;
  modules: number;
  entities: number;
  functionalities: number;
  decisions: number;
  discarded: { kind: string; name: string; reason: string }[];
  skipped: { ref: string; stage: string; reason: string }[];
}

export interface IntrospectionSource {
  alias: string;
  host: string;
}
