// Tipos del contrato ApiArtifact v1.0.0 (espejo de los esquemas Pydantic).
// Claves en inglés (contrato); campos opcionales para tolerar variaciones.

import type { RiskSeverity } from "@/lib/types/arquitectura";
import type { LogicalType } from "@/lib/types/bd";
import type {
  JobStatus,
  JobStatusCounts,
  JobStatusGroup,
  Origin,
  QuestionStatus,
  SourceType,
} from "@/lib/types/ef";

export type ApiStyle = "rest" | "graphql" | "grpc" | "soap";
export type AuthScheme = "bearer_jwt" | "oauth2_oidc" | "api_key" | "none";
export type HttpMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

/** Cuánto se publica de un recurso. Todo lo que no sea `crud` lleva motivo. */
export type ResourceExposure = "crud" | "read_only" | "nested_only" | "none";

export type EndpointKind =
  | "list"
  | "read_item"
  | "create"
  | "update"
  | "delete"
  | "action"
  | "nested_list"
  | "nested_create"
  | "nested_delete";

export type SchemaKind =
  | "create"
  | "update"
  | "read"
  | "list_item"
  | "action_input"
  | "error"
  | "envelope";

export type ParameterLocation = "path" | "query" | "header";
export type ResponseKind = "item" | "page" | "none";

export type AuthEffect = "allow" | "deny";
/** Alcance por filas. Todo lo distinto de `all`/`none` exige columna real. */
export type AuthScope =
  | "all"
  | "own"
  | "own_team"
  | "own_branch"
  | "custom"
  | "none";
export type AuthBasis =
  | "crud_matrix"
  | "business_rule"
  | "inferred"
  | "default_deny";

/** Dónde hace cumplir la API una regla del EF. */
export type ApiRuleEnforcement =
  | "endpoint"
  | "schema"
  | "authorization"
  | "database"
  | "not_applicable";

export interface ApiSourceRef {
  bd_job_id: string;
  bd_artifact_hash: string;
  bd_schema_version?: string;
  architecture_job_id?: string | null;
  architecture_artifact_hash?: string | null;
  scrum_job_id?: string | null;
  scrum_artifact_hash?: string | null;
  ef_job_id: string;
  ef_artifact_hash: string;
  ef_schema_version?: string;
  ready_snapshot: boolean;
}

export interface ApiAuthConfig {
  scheme: AuthScheme;
  provider?: string | null;
  source_ref?: string | null;
  decided: boolean;
}

export interface ApiPagination {
  style: string;
  limit_param: string;
  offset_param: string;
  default_limit: number;
  max_limit: number;
  items_field: string;
  total_field: string;
}

export interface ApiConventions {
  path_language: string;
  path_case: string;
  resource_number: string;
  property_case: string;
  envelope: string;
  update_verb: HttpMethod;
  max_nesting: number;
  pagination: ApiPagination;
  sort_param: string;
  date_format: string;
  decimal_as_string: boolean;
}

export interface ApiTarget {
  api_style: ApiStyle;
  spec_version: string;
  base_path: string;
  api_version: string;
  versioning: string;
  auth: ApiAuthConfig;
  conventions: ApiConventions;
  conventions_source?: string | null;
}

export interface ApiResource {
  id: string;
  name: string;
  singular: string;
  display_name?: string | null;
  description?: string | null;
  table_ref: string;
  entity_ref?: string | null;
  component_ref?: string | null;
  base_path: string;
  exposure: ResourceExposure;
  exposure_reason?: string | null;
  parent_resource_ref?: string | null;
  source_refs: string[];
  confidence?: number | null;
  origin?: Origin | null;
}

export interface ApiSchemaField {
  id: string;
  name: string;
  logical_type: LogicalType;
  format?: string | null;
  required: boolean;
  nullable: boolean;
  read_only: boolean;
  write_only: boolean;
  max_length?: number | null;
  enum?: string[] | null;
  description?: string | null;
  example?: string | null;
  /** Columna del modelo de datos que lo origina. Sin ella no existe el campo. */
  column_ref?: string | null;
  table_ref?: string | null;
  computed: boolean;
  pii: boolean;
  source_refs: string[];
  confidence?: number | null;
  origin?: Origin | null;
}

export interface ApiDataSchema {
  id: string;
  name: string;
  kind: SchemaKind;
  resource_ref?: string | null;
  description?: string | null;
  fields: ApiSchemaField[];
  source_refs: string[];
  confidence?: number | null;
  origin?: Origin | null;
}

export interface ApiParameter {
  id: string;
  name: string;
  location: ParameterLocation;
  logical_type: LogicalType;
  required: boolean;
  description?: string | null;
  example?: string | null;
  column_ref?: string | null;
}

export interface ApiStatusCode {
  code: number;
  description?: string | null;
  schema_ref?: string | null;
  error_ref?: string | null;
}

export interface ApiEndpoint {
  id: string;
  resource_ref: string;
  method: HttpMethod;
  path: string;
  operation_id: string;
  kind: EndpointKind;
  purpose: string;
  description?: string | null;
  parameters: ApiParameter[];
  request_schema_ref?: string | null;
  response_schema_ref?: string | null;
  response_kind: ResponseKind;
  status_codes: ApiStatusCode[];
  filters: string[];
  sortable: string[];
  paginated: boolean;
  idempotent: boolean;
  deprecated: boolean;
  auth_rule_refs: string[];
  rule_refs: string[];
  ef_api_ref?: string | null;
  source_refs: string[];
  confidence?: number | null;
  origin?: Origin | null;
}

export interface ApiAuthorizationRule {
  id: string;
  endpoint_ref: string;
  actor_ref: string;
  actor_name?: string | null;
  effect: AuthEffect;
  scope: AuthScope;
  scope_expression?: string | null;
  scope_column_refs: string[];
  basis: AuthBasis;
  /** El alcance no se puede aplicar con lo que hay: pregunta bloqueante. */
  ambiguous: boolean;
  note?: string | null;
  source_refs: string[];
  confidence?: number | null;
  origin?: Origin | null;
}

export interface ApiErrorEntry {
  id: string;
  status: number;
  code: string;
  message: string;
  when?: string | null;
  source_refs: string[];
}

export interface ApiRuleMapping {
  id: string;
  rule_ref: string;
  enforcement: ApiRuleEnforcement;
  endpoint_refs: string[];
  schema_field_refs: string[];
  auth_rule_refs: string[];
  /** Lo que decidió el Agente BD sobre la misma regla. */
  bd_enforcement?: string | null;
  note?: string | null;
  confidence?: number | null;
  origin?: Origin | null;
}

export interface OpenApiDocumentBlock {
  format: "yaml" | "json";
  spec_version: string;
  content: string;
  operations_total: number;
  byte_size: number;
  checksum?: string | null;
}

export interface SpecValidationIssue {
  code: string;
  message: string;
  ref?: string | null;
}

export interface SpecValidation {
  spec_valid: boolean;
  validator?: string | null;
  validator_version?: string | null;
  /** Distingue "parseado" de "un runtime real lo usó". */
  runtime_checked: boolean;
  checks: Record<string, boolean>;
  errors: SpecValidationIssue[];
  warnings: SpecValidationIssue[];
}

export interface ApiRisk {
  id: string;
  description: string;
  severity: RiskSeverity;
  mitigation?: string | null;
  source_ref?: string | null;
  confidence?: number | null;
  origin?: Origin | null;
}

export interface ApiObservation {
  id: string;
  description: string;
  reason?: string | null;
}

export interface ApiCoverage {
  tables_total: number;
  tables_exposed: number;
  unexposed_table_refs: string[];
  ef_apis_total: number;
  ef_apis_covered: number;
  uncovered_api_refs: string[];
  crud_cells_total: number;
  crud_cells_covered: number;
  uncovered_crud_refs: string[];
  rules_total: number;
  rules_enforced: number;
  unenforced_rule_refs: string[];
  actors_total: number;
  actors_with_access: number;
  actors_without_access: string[];
}

export interface ApiAnalysis {
  risks: ApiRisk[];
  observations: ApiObservation[];
  coverage: ApiCoverage;
}

export interface TechLeadQuestion {
  id: string;
  question: string;
  reason: string;
  audience: "negocio" | "tecnico";
  blocking: boolean;
  linked_to_ref?: string | null;
  status: QuestionStatus;
  confidence?: number | null;
  origin?: Origin | null;
}

export interface ApiMetrics {
  tokens: { input: number; output: number; total: number };
  cost: number;
  duration: number;
  resources_total: number;
  endpoints_total: number;
  schemas_total: number;
  auth_rules_total: number;
  coverage: number;
  spec_valid: boolean;
  endpoints_unauthorized: number;
  skipped: { ref: string; stage: string; reason: string }[];
}

export interface ApiArtifact {
  schema_version: string;
  source: ApiSourceRef;
  target: ApiTarget;
  resources: ApiResource[];
  schemas: ApiDataSchema[];
  endpoints: ApiEndpoint[];
  authorization_matrix: ApiAuthorizationRule[];
  error_catalog: ApiErrorEntry[];
  rule_mappings: ApiRuleMapping[];
  openapi: OpenApiDocumentBlock;
  validation: SpecValidation;
  analysis: ApiAnalysis;
  questions_for_tech_lead: TechLeadQuestion[];
  metrics: ApiMetrics;
}

// --- Respuestas de la API -----------------------------------------------------

export interface SpecResult {
  job_id: string;
  status: JobStatus;
  input_job_id: string;
}

export interface ApiJobDetail {
  job_id: string;
  status: JobStatus;
  parent_job_id?: string | null;
  input_job_id?: string | null;
  error?: string | null;
  metrics?: Record<string, unknown> | null;
}

export interface ApiJobListItem {
  job_id: string;
  title?: string | null;
  source_type: SourceType;
  status: JobStatus;
  version: number;
  parent_job_id?: string | null;
  input_job_id?: string | null;
  created_at?: string | null;
  completed_at?: string | null;
}

export interface ApiJobList {
  total: number;
  limit: number;
  offset: number;
  estado: JobStatusGroup;
  status_counts: JobStatusCounts;
  items: ApiJobListItem[];
}

export interface AvailableBdJob {
  job_id: string;
  title?: string | null;
  status: JobStatus;
  ready_for_next_stage: boolean;
  blocking_pending: string[];
}

export interface ApiValidationSummary {
  validations: {
    target_id: string;
    target_type: string;
    status: QuestionStatus;
    respuesta?: string | null;
  }[];
  blocking_total: number;
  blocking_pending: string[];
  checks: Record<string, boolean>;
  ready_for_next_stage: boolean;
}

export interface OpenApiExport {
  format: "yaml" | "json";
  spec_version?: string | null;
  operations_total: number;
  checksum?: string | null;
  valid: boolean;
  content: string;
}
