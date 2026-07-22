// Tipos del contrato ArchitectureArtifact v1.0.0 (espejo de los esquemas Pydantic).
// Claves en inglés (contrato); campos opcionales para tolerar variaciones.

import type {
  JobStatus,
  Origin,
  QuestionStatus,
  SourceType,
} from "@/lib/types/ef";

export type Audience = "negocio" | "tecnico";
export type ArchitectureStyleName =
  | "modular_monolith"
  | "microservices"
  | "serverless";
export type SizeClass = "S" | "M" | "L";
export type ComponentType =
  | "ui"
  | "api"
  | "service"
  | "domain"
  | "integration"
  | "datastore"
  | "worker";
export type IntegrationDirection = "inbound" | "outbound" | "bidirectional";
export type IntegrationProtocol =
  | "rest"
  | "soap"
  | "file"
  | "db"
  | "queue"
  | "unknown";
export type ContractKind =
  | "sync_api"
  | "event"
  | "shared_module"
  | "file"
  | "external";
export type CrossCuttingConcern =
  | "auth"
  | "authorization"
  | "audit"
  | "notifications"
  | "logging"
  | "config"
  | "error_handling"
  | "i18n";
export type RiskSeverity = "alta" | "media" | "baja";
export type AdrStatus = "proposed" | "accepted" | "superseded";

export interface ArchSource {
  scrum_job_id: string;
  scrum_artifact_hash: string;
  scrum_schema_version: string;
  ef_job_id: string;
  ef_artifact_hash: string;
  ef_schema_version: string;
  ready_snapshot: boolean;
}

export interface ScopeProfile {
  entities: number;
  relationships: number;
  modules: number;
  processes: number;
  stories: number;
  points_total: number;
  integrations_detected: number;
  nfr_count: number;
}

export interface BoundedContext {
  id: string;
  name: string;
  source_refs: string[];
  confidence?: number | null;
  origin?: Origin | null;
}

export interface ArchitectureContext {
  scope_profile: ScopeProfile;
  size_class: SizeClass;
  bounded_contexts: BoundedContext[];
}

export interface StyleDecision {
  chosen: ArchitectureStyleName;
  rationale: string;
  adr_ref?: string | null;
  confidence?: number | null;
  origin?: Origin | null;
}

export interface ComponentSourceRefs {
  epic_refs: string[];
  story_refs: string[];
  entity_refs: string[];
  api_refs: string[];
  module_refs: string[];
  process_refs: string[];
}

export interface ArchComponent {
  id: string;
  name: string;
  type: ComponentType;
  layer: string;
  responsibility: string;
  source_refs: ComponentSourceRefs;
  depends_on: string[];
  confidence?: number | null;
  origin?: Origin | null;
}

export interface StackChoice {
  id: string;
  layer: string;
  technology: string;
  version?: string | null;
  rationale: string;
  alternatives: string[];
  source_refs: string[];
  confidence?: number | null;
  origin?: Origin | null;
}

export interface Adr {
  id: string;
  title: string;
  decision: string;
  context: string;
  alternatives_considered: string[];
  consequences: string[];
  status: AdrStatus;
  source_refs: string[];
  confidence?: number | null;
  origin?: Origin | null;
}

export interface Integration {
  id: string;
  name: string;
  system: string;
  direction: IntegrationDirection;
  protocol: IntegrationProtocol;
  purpose: string;
  data_exchanged?: string | null;
  source_refs: string[];
  contract_known: boolean;
  confidence?: number | null;
  origin?: Origin | null;
}

export interface Contract {
  id: string;
  from_ref: string;
  to_ref: string;
  kind: ContractKind;
  description: string;
  source_refs: string[];
  confidence?: number | null;
  origin?: Origin | null;
}

export interface CrossCutting {
  id: string;
  concern: CrossCuttingConcern;
  requirement: string;
  approach: string;
  source_refs: string[];
  confidence?: number | null;
  origin?: Origin | null;
}

export interface Diagram {
  format: "mermaid";
  code: string;
}

export interface Diagrams {
  component?: Diagram | null;
  context?: Diagram | null;
}

export interface ArchRisk {
  id: string;
  description: string;
  severity: RiskSeverity;
  mitigation?: string | null;
  source_ref?: string | null;
  confidence?: number | null;
  origin?: Origin | null;
}

export interface ArchObservation {
  id: string;
  description: string;
  reason?: string | null;
}

export interface ArchCoverage {
  epics_total: number;
  epics_mapped: number;
  uncovered_epic_refs: string[];
  entities_total: number;
  entities_mapped: number;
  uncovered_entity_refs: string[];
  nfr_total: number;
  nfr_addressed: number;
  uncovered_nfr_refs: string[];
}

export interface ArchAnalysis {
  risks: ArchRisk[];
  observations: ArchObservation[];
  coverage: ArchCoverage;
}

export interface ArchitectQuestion {
  id: string;
  question: string;
  reason: string;
  audience: Audience;
  blocking: boolean;
  linked_to_ref?: string | null;
  status: QuestionStatus;
  confidence?: number | null;
  origin?: Origin | null;
}

export interface ArchMetrics {
  tokens: { input: number; output: number; total: number };
  cost: number;
  duration: number;
  components_total: number;
  adrs_total: number;
  integrations_total: number;
  coverage: number;
  skipped?: { ref: string; stage: string; reason: string }[];
}

export interface ArchitectureArtifact {
  schema_version: string;
  source: ArchSource;
  context: ArchitectureContext;
  architecture_style?: StyleDecision | null;
  components: ArchComponent[];
  stack: StackChoice[];
  adrs: Adr[];
  integrations: Integration[];
  contracts: Contract[];
  cross_cutting: CrossCutting[];
  diagrams: Diagrams;
  analysis: ArchAnalysis;
  questions_for_architect: ArchitectQuestion[];
  metrics: ArchMetrics;
}

// --- Tipos de la API ---

export interface ArchJobDetail {
  job_id: string;
  status: JobStatus;
  parent_job_id?: string | null;
  input_job_id?: string | null;
  error?: string | null;
  metrics?: ArchMetrics | null;
}

export interface ArchJobListItem {
  job_id: string;
  title?: string | null;
  source_type?: SourceType | null;
  status: JobStatus;
  version?: number | null;
  parent_job_id?: string | null;
  input_job_id?: string | null;
  created_at?: string | null;
  completed_at?: string | null;
}

export interface ArchJobList {
  total: number;
  limit: number;
  offset: number;
  items: ArchJobListItem[];
}

export interface DesignResult {
  job_id: string;
  status: JobStatus;
  input_job_id: string;
}

export interface AvailableScrumJob {
  job_id: string;
  status: JobStatus;
  ready_for_next_stage: boolean;
  blocking_pending: string[];
}

export interface ArchChecks {
  no_blocking_questions: boolean;
  style_decided: boolean;
  has_components: boolean;
  coverage_met: boolean;
}

export interface ArchValidationRecord {
  target_type: string;
  target_id: string;
  status: QuestionStatus;
  respuesta?: string | null;
}

export interface ArchValidationSummary {
  total: number;
  by_status: Record<string, number>;
  by_target_type: Record<string, number>;
  validations: ArchValidationRecord[];
  blocking_total: number;
  blocking_pending: string[];
  checks: ArchChecks;
  ready_for_next_stage: boolean;
}
