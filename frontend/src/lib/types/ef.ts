// Tipos del contrato EFArtifact v1.2.0 (espejo de los esquemas Pydantic).
// Claves en inglés (contrato). Campos nuevos son opcionales para tolerar
// artefactos previos.

export type Origin = "stated" | "derived";
export type Audience = "negocio" | "tecnico";
export type Cardinality = "1:1" | "1:N" | "N:M";
export type QuestionStatus = "pendiente" | "confirmado" | "corregido";
export type Priority = "alta" | "media" | "baja";
export type HttpMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
export type SourceType = "document" | "text";
export type SourceFidelity = "full" | "partial" | "degraded";

export type JobStatus =
  | "PENDING"
  | "RUNNING"
  | "NEEDS_INPUT"
  | "COMPLETED"
  | "COMPLETED_WITH_WARNINGS"
  | "FAILED";

export interface TracedItem {
  id: string;
  source_ref?: string | null;
  evidence?: string | null;
  confidence?: number | null;
  origin?: Origin | null;
}

export interface SourceInfo {
  type: SourceType;
  hash: string;
  fidelity: SourceFidelity;
  filename?: string | null;
}

export interface Requirement extends TracedItem {
  text: string;
  priority?: Priority | null;
}

export interface RequirementsBlock {
  business: Requirement[];
  functional: Requirement[];
  non_functional: Requirement[];
}

export interface Actor extends TracedItem {
  name: string;
  description?: string | null;
  responsibilities?: string[];
}

export interface ModuleItem extends TracedItem {
  name: string;
  description?: string | null;
}

export interface Menu extends TracedItem {
  name: string;
  module_ref?: string | null;
  parent_ref?: string | null;
  path?: string | null;
}

export interface Process extends TracedItem {
  name: string;
  description?: string | null;
  steps?: string[];
  actor_refs?: string[];
}

export interface BusinessRule extends TracedItem {
  statement: string;
}

export interface ValidationRule extends TracedItem {
  rule: string;
  field_ref?: string | null;
}

export interface FieldDef extends TracedItem {
  name: string;
  entity_ref?: string | null;
  data_type?: string | null;
  required: boolean;
}

export interface Entity extends TracedItem {
  name: string;
  description?: string | null;
  origin: Origin;
}

export interface Relationship extends TracedItem {
  source_entity_ref: string;
  target_entity_ref: string;
  cardinality: Cardinality;
  name?: string | null;
}

export interface CrudMatrixEntry extends TracedItem {
  entity_ref: string;
  actor_ref?: string | null;
  module_ref?: string | null;
  create: boolean;
  read: boolean;
  update: boolean;
  delete: boolean;
}

export interface ApiEndpoint extends TracedItem {
  method: HttpMethod;
  path: string;
  description?: string | null;
  entity_ref?: string | null;
}

export interface ScopeItem {
  id?: string | null;
  description: string;
  requirement_refs?: string[];
  reason?: string | null;
}

export interface Assumption extends TracedItem {
  assumption: string;
  rationale?: string | null;
}

export interface SystemsInterpretation {
  what_process_requests: string;
  scope_for_systems?: ScopeItem[];
  apparent_out_of_scope?: ScopeItem[];
  interpretation_assumptions?: Assumption[];
}

export interface Ambiguity extends TracedItem {
  description: string;
}

export interface MissingInfo extends TracedItem {
  description: string;
  expected_where?: string | null;
}

export interface Inconsistency extends TracedItem {
  description: string;
  conflicting_refs?: string[];
}

export interface Observation extends TracedItem {
  description: string;
  reason?: string | null;
}

export interface Analysis {
  ambiguities?: Ambiguity[];
  missing_info?: MissingInfo[];
  inconsistencies?: Inconsistency[];
  observations?: Observation[];
}

export interface Question extends TracedItem {
  question: string;
  reason: string;
  audience: Audience;
  blocking: boolean;
  linked_to_ref?: string | null;
  status: QuestionStatus;
}

export interface TokenMetrics {
  input: number;
  output: number;
  total: number;
}

export interface SkippedItem {
  ref: string;
  stage: string;
  reason: string;
}

export interface Metrics {
  tokens: TokenMetrics;
  cost: number;
  duration: number;
  chunks_total: number;
  chunks_skipped: number;
  coverage: number;
  skipped?: SkippedItem[];
}

export interface EFArtifact {
  schema_version: string;
  source: SourceInfo;
  summary: string;
  requirements: RequirementsBlock;
  actors: Actor[];
  modules: ModuleItem[];
  menus: Menu[];
  processes: Process[];
  business_rules: BusinessRule[];
  validations: ValidationRule[];
  fields: FieldDef[];
  entities: Entity[];
  relationships: Relationship[];
  crud: CrudMatrixEntry[];
  apis: ApiEndpoint[];
  systems_interpretation: SystemsInterpretation;
  analysis: Analysis;
  questions_for_analyst: Question[];
  metrics: Metrics;
}

// --- Tipos de la API (jobs, validaciones) ---

export interface JobDetail {
  job_id: string;
  status: JobStatus;
  parent_job_id?: string | null;
  error?: string | null;
  metrics?: Metrics | null;
  source_doc_id?: string;
}

export interface JobListItem {
  job_id: string;
  status: JobStatus;
  parent_job_id?: string | null;
}

export interface JobList {
  total: number;
  limit: number;
  offset: number;
  items: JobListItem[];
}

export interface AnalyzeResult {
  job_id: string;
  status: JobStatus;
  cached: boolean;
}

export interface ValidationRecord {
  target_type: "question" | "assumption";
  target_id: string;
  status: QuestionStatus;
  respuesta?: string | null;
}

export interface ValidationSummary {
  total: number;
  by_status: Record<string, number>;
  by_target_type: Record<string, number>;
  validations: ValidationRecord[];
  blocking_total: number;
  blocking_pending: string[];
  ready_for_next_stage: boolean;
}

export interface RefineResult {
  job_id: string;
  parent_job_id: string;
}
