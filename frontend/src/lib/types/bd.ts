// Tipos del contrato DatabaseArtifact v1.0.0 (espejo de los esquemas Pydantic).
// Claves en inglés (contrato); campos opcionales para tolerar variaciones.

import type {
  ReconciliationRef,
  ReconciliationSummary,
} from "@/lib/reconciliation";
import type {
  JobStatus,
  Origin,
  QuestionStatus,
  SourceType,
} from "@/lib/types/ef";
import type { RiskSeverity } from "@/lib/types/arquitectura";

export type DbEngine = "postgresql" | "sqlserver" | "oracle" | "mysql";

/** Tipo lógico neutro de motor: el DDL lo traduce al dialecto destino. */
export type LogicalType =
  | "string"
  | "text"
  | "integer"
  | "bigint"
  | "decimal"
  | "boolean"
  | "date"
  | "time"
  | "timestamp"
  | "timestamptz"
  | "uuid"
  | "json"
  | "binary";

export type TableKind = "entity" | "junction" | "catalog" | "audit";
export type PrimaryKeyStrategy =
  | "surrogate"
  | "surrogate_uuid"
  | "natural"
  | "composite";
export type ReferentialAction = "cascade" | "restrict" | "set_null" | "no_action";
/** Dónde se hace cumplir una regla del EF. */
export type RuleEnforcement = "declarative" | "application" | "trigger";
export type DdlScriptKind =
  | "schema"
  | "tables"
  | "constraints"
  | "indexes"
  | "seed"
  | "rollback";

export interface DbSource {
  architecture_job_id: string;
  architecture_artifact_hash: string;
  architecture_schema_version: string;
  scrum_job_id?: string | null;
  scrum_artifact_hash?: string | null;
  ef_job_id: string;
  ef_artifact_hash: string;
  ef_schema_version: string;
  ready_snapshot: boolean;
}

export interface DbConventions {
  naming_case: string;
  table_number: string;
  pk_strategy: PrimaryKeyStrategy;
  fk_pattern: string;
  audit_columns: boolean;
  soft_delete: boolean;
  schema_name: string;
}

export interface DbTarget {
  engine: DbEngine;
  engine_version?: string | null;
  engine_source_ref?: string | null;
  /** `false` si la arquitectura no decidió motor y se usó un fallback. */
  engine_decided: boolean;
  conventions: DbConventions;
  conventions_source?: string | null;
}

export interface DbColumn {
  id: string;
  name: string;
  ordinal: number;
  logical_type: LogicalType;
  /** Tipo físico ya renderizado al motor (lo escribe DDL_GEN). */
  type?: string | null;
  length?: number | null;
  precision?: number | null;
  scale?: number | null;
  nullable: boolean;
  default?: string | null;
  is_primary_key: boolean;
  is_generated: boolean;
  description?: string | null;
  example?: string | null;
  field_ref?: string | null;
  source_refs: string[];
  /** El EF no permitía deducir el tipo: hay una pregunta ligada. */
  type_ambiguous: boolean;
  /** Candidata a dato personal (lo marca CRITIQUE). */
  pii: boolean;
  confidence?: number | null;
  origin?: Origin | null;
}

export interface DbPrimaryKey {
  name: string;
  columns: string[];
  strategy: PrimaryKeyStrategy;
  rationale?: string | null;
  origin?: Origin | null;
}

export interface DbForeignKey {
  id: string;
  name: string;
  columns: string[];
  references_table: string;
  references_columns: string[];
  on_delete: ReferentialAction;
  on_update: ReferentialAction;
  relationship_ref?: string | null;
  rationale?: string | null;
  source_refs: string[];
  confidence?: number | null;
  origin?: Origin | null;
}

export interface DbUniqueConstraint {
  id: string;
  name: string;
  columns: string[];
  description?: string | null;
  source_refs: string[];
  confidence?: number | null;
  origin?: Origin | null;
}

export interface DbCheckConstraint {
  id: string;
  name: string;
  expression: string;
  description?: string | null;
  source_refs: string[];
  confidence?: number | null;
  origin?: Origin | null;
}

export interface DbIndex {
  id: string;
  name: string;
  columns: string[];
  unique: boolean;
  rationale: string;
  access_pattern_refs: string[];
  source_refs: string[];
  confidence?: number | null;
  origin?: Origin | null;
}

export interface DbNormalization {
  form: string;
  denormalized: boolean;
  rationale?: string | null;
}

export interface DbTable {
  id: string;
  name: string;
  schema_name?: string | null;
  entity_ref?: string | null;
  kind: TableKind;
  description?: string | null;
  columns: DbColumn[];
  primary_key?: DbPrimaryKey | null;
  foreign_keys: DbForeignKey[];
  unique_constraints: DbUniqueConstraint[];
  check_constraints: DbCheckConstraint[];
  indexes: DbIndex[];
  estimated_volume: "baja" | "media" | "alta" | "desconocida";
  normalization: DbNormalization;
  source_refs: string[];
  confidence?: number | null;
  origin?: Origin | null;
  /** Veredicto de RECONCILE (INV4). Ausente si la fase no corrió. */
  reconciliation?: ReconciliationRef | null;
}

export interface DbDdlScript {
  id: string;
  order: number;
  name: string;
  kind: DdlScriptKind;
  engine: DbEngine;
  statements: string[];
  sql: string;
  source_refs: string[];
}

export interface DbSeedData {
  id: string;
  table_ref: string;
  table: string;
  reason?: string | null;
  columns: string[];
  rows: Record<string, unknown>[];
  source_refs: string[];
  /** Cita textual del EF: sin ella no se emiten valores. */
  evidence?: string | null;
  confidence?: number | null;
  origin?: Origin | null;
}

export interface DbDictionaryEntry {
  id: string;
  table: string;
  column: string;
  type: string;
  nullable: boolean;
  key: string;
  description?: string | null;
  example?: string | null;
  source_refs: string[];
  origin?: Origin | null;
}

export interface DbErDiagram {
  format: "mermaid";
  code: string;
}

export interface DbDesignDecision {
  id: string;
  title: string;
  decision: string;
  rationale: string;
  alternatives_considered: string[];
  consequences: string[];
  scope: "global" | "table";
  table_refs: string[];
  source_refs: string[];
  confidence?: number | null;
  origin?: Origin | null;
}

export interface DbRuleMapping {
  id: string;
  rule_ref: string;
  enforcement: RuleEnforcement;
  constraint_ref?: string | null;
  table_ref?: string | null;
  note?: string | null;
  confidence?: number | null;
  origin?: Origin | null;
}

export interface DbValidationIssue {
  code: string;
  message: string;
  ref?: string | null;
}

export interface DbDdlValidation {
  syntax_ok: boolean;
  engine?: DbEngine | null;
  validator?: string | null;
  /** `false` = solo se parseó; no se ejecutó contra un motor real. */
  executed: boolean;
  checks: Record<string, boolean>;
  errors: DbValidationIssue[];
  warnings: DbValidationIssue[];
}

export interface DbaQuestion {
  id: string;
  question: string;
  reason: string;
  audience: "tecnico" | "negocio";
  blocking: boolean;
  linked_to_ref?: string | null;
  status: QuestionStatus;
  confidence?: number | null;
  origin?: Origin | null;
}

export interface DbRisk {
  id: string;
  description: string;
  severity: RiskSeverity;
  mitigation?: string | null;
  source_ref?: string | null;
  confidence?: number | null;
  origin?: Origin | null;
}

export interface DbObservation {
  id: string;
  description: string;
  reason?: string | null;
}

export interface DbCoverage {
  entities_total: number;
  entities_mapped: number;
  uncovered_entity_refs: string[];
  fields_total: number;
  fields_mapped: number;
  unmapped_field_refs: string[];
  validations_total: number;
  validations_enforced: number;
  unenforced_validation_refs: string[];
  rules_total: number;
  rules_enforced: number;
  unenforced_rule_refs: string[];
}

export interface DbAnalysis {
  risks: DbRisk[];
  observations: DbObservation[];
  coverage: DbCoverage;
}

export interface DbMetrics {
  tokens: { input: number; output: number; total: number };
  cost: number;
  duration: number;
  tables_total: number;
  columns_total: number;
  indexes_total: number;
  constraints_total: number;
  seed_rows_total: number;
  coverage: number;
  ddl_valid: boolean;
  skipped: { ref: string; stage: string; reason: string }[];
}

export interface DatabaseArtifact {
  schema_version: string;
  source: DbSource;
  target: DbTarget;
  tables: DbTable[];
  ddl_scripts: DbDdlScript[];
  seed_data: DbSeedData[];
  data_dictionary: DbDictionaryEntry[];
  er_diagram: DbErDiagram;
  design_decisions: DbDesignDecision[];
  rule_mappings: DbRuleMapping[];
  validation: DbDdlValidation;
  analysis: DbAnalysis;
  questions_for_dba: DbaQuestion[];
  metrics: DbMetrics;
  /** Resumen de RECONCILE (INV4). Ausente en artefactos anteriores al módulo. */
  reconciliation?: ReconciliationSummary | null;
}

// --- Envolturas de la API ----------------------------------------------------

export interface DbJobDetail {
  job_id: string;
  status: JobStatus;
  parent_job_id?: string | null;
  input_job_id?: string | null;
  error?: string | null;
  metrics?: Record<string, unknown> | null;
}

export interface DbJobListItem {
  job_id: string;
  title?: string | null;
  source_type?: SourceType | null;
  status: JobStatus;
  version?: number;
  parent_job_id?: string | null;
  input_job_id?: string | null;
  created_at?: string | null;
  completed_at?: string | null;
}

export interface DbJobList {
  total: number;
  limit: number;
  offset: number;
  items: DbJobListItem[];
}

export interface ModelResult {
  job_id: string;
  status: JobStatus;
  input_job_id: string;
}

export interface AvailableArchitectureJob {
  job_id: string;
  title?: string | null;
  status: JobStatus;
  ready_for_next_stage: boolean;
  blocking_pending: string[];
}

export interface DbChecks {
  no_blocking_questions: boolean;
  has_tables: boolean;
  all_tables_have_pk: boolean;
  coverage_met: boolean;
  ddl_valid: boolean;
}

export interface DbValidationRecord {
  target_type: string;
  target_id: string;
  status: QuestionStatus;
  respuesta?: string | null;
}

export interface DbValidationSummary {
  total: number;
  by_status: Record<string, number>;
  by_target_type: Record<string, number>;
  validations: DbValidationRecord[];
  blocking_total: number;
  blocking_pending: string[];
  checks: DbChecks;
  ready_for_next_stage: boolean;
}

export interface DdlExport {
  engine: DbEngine;
  /** Motor con el que se generó el artefacto (el de registro). */
  engine_of_record: DbEngine;
  /** `true` si se re-renderizó a un motor distinto (sin llamar al modelo). */
  regenerated: boolean;
  scripts: DbDdlScript[];
  sql: string;
}
