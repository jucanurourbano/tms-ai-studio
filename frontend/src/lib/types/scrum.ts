// Tipos del contrato ScrumArtifact v1.0.0 (espejo de los esquemas Pydantic).
// Claves en inglés (contrato); campos opcionales para tolerar variaciones.

import type {
  JobStatus,
  Origin,
  QuestionStatus,
  SourceType,
} from "@/lib/types/ef";

export type Audience = "negocio" | "tecnico";
export type MoscowPriority = "must" | "should" | "could" | "wont";
export type StoryPoints = 1 | 2 | 3 | 5 | 8 | 13 | 21;
export type AcceptanceFormat = "gherkin" | "text";
export type RiskSeverity = "alta" | "media" | "baja";
export type BacklogMethod = "moscow" | "value_effort";

export interface SourceRef {
  ef_job_id: string;
  ef_artifact_hash: string;
  ef_schema_version: string;
  ready_snapshot: boolean;
}

export interface Epic {
  id: string;
  title: string;
  description?: string | null;
  source_refs: string[];
  story_ids: string[];
  confidence?: number | null;
  origin?: Origin | null;
}

export interface StorySourceRefs {
  requirement_refs: string[];
  process_refs: string[];
  rule_refs: string[];
}

export interface AcceptanceCriterion {
  id: string;
  format: AcceptanceFormat;
  given?: string | null;
  when?: string | null;
  then?: string | null;
  text?: string | null;
  source_refs: string[];
  origin?: Origin | null;
}

export interface Story {
  id: string;
  role: string;
  goal: string;
  benefit: string;
  statement: string;
  epic_ref?: string | null;
  source_refs: StorySourceRefs;
  acceptance_criteria: AcceptanceCriterion[];
  story_points?: StoryPoints | null;
  estimation_rationale?: string | null;
  estimation_confidence?: number | null;
  priority?: MoscowPriority | null;
  value?: number | null;
  effort?: number | null;
  dependencies: string[];
  tags: string[];
  external_key?: string | null;
  confidence?: number | null;
  origin?: Origin | null;
}

export interface ProductBacklog {
  method: BacklogMethod;
  ordered_story_ids: string[];
  rationale?: string | null;
}

export interface Sprint {
  id: string;
  goal?: string | null;
  capacity_points: number;
  total_points: number;
  story_ids: string[];
}

export interface PoQuestion {
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

export interface Risk {
  id: string;
  description: string;
  severity: RiskSeverity;
  source_ref?: string | null;
}

export interface Observation {
  id: string;
  description: string;
  reason?: string | null;
}

export interface Coverage {
  requirements_total: number;
  requirements_covered: number;
  coverage_ratio: number;
  uncovered_requirement_refs: string[];
}

export interface ScrumAnalysis {
  risks: Risk[];
  observations: Observation[];
  coverage: Coverage;
}

export interface ScrumMetrics {
  tokens: { input: number; output: number; total: number };
  cost: number;
  duration: number;
  stories_total: number;
  points_total: number;
  sprints_total: number;
  coverage: number;
  skipped?: { ref: string; stage: string; reason: string }[];
}

export interface ScrumArtifact {
  schema_version: string;
  source: SourceRef;
  epics: Epic[];
  stories: Story[];
  product_backlog: ProductBacklog;
  sprints: Sprint[];
  unassigned_story_ids: string[];
  questions_for_po: PoQuestion[];
  analysis: ScrumAnalysis;
  metrics: ScrumMetrics;
}

// --- Tipos de la API ---

export interface ScrumJobDetail {
  job_id: string;
  status: JobStatus;
  parent_job_id?: string | null;
  input_job_id?: string | null;
  error?: string | null;
  metrics?: ScrumMetrics | null;
}

export interface ScrumJobListItem {
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

export interface ScrumJobList {
  total: number;
  limit: number;
  offset: number;
  items: ScrumJobListItem[];
}

export interface PlanResult {
  job_id: string;
  status: JobStatus;
  input_job_id: string;
}

export interface AvailableEfJob {
  job_id: string;
  status: JobStatus;
  ready_for_next_stage: boolean;
  blocking_pending: string[];
}

export interface ScrumChecks {
  no_blocking_questions: boolean;
  must_should_estimated: boolean;
  coverage_met: boolean;
  no_must_unassigned: boolean;
}

export interface ScrumValidationRecord {
  target_type: string;
  target_id: string;
  status: QuestionStatus;
  respuesta?: string | null;
}

export interface ScrumValidationSummary {
  total: number;
  by_status: Record<string, number>;
  by_target_type: Record<string, number>;
  validations: ScrumValidationRecord[];
  blocking_total: number;
  blocking_pending: string[];
  checks: ScrumChecks;
  ready_for_next_stage: boolean;
}

export interface ScrumExport {
  format: "csv" | "json";
  filename: string;
  content: string | Record<string, unknown>[];
}
