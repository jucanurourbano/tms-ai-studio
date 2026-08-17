// Tipos del contrato QaArtifact v1.0.0 (espejo de los esquemas Pydantic).
// Claves en inglés (contrato); campos opcionales para tolerar variaciones.

import type { AuthScope } from "@/lib/types/api";
import type { RiskSeverity } from "@/lib/types/arquitectura";
import type {
  JobStatus,
  JobStatusCounts,
  JobStatusGroup,
  Origin,
  QuestionStatus,
  SourceType,
} from "@/lib/types/ef";
import type { MoscowPriority } from "@/lib/types/scrum";

/** Clase de caso. Cada tipo tiene una fuente distinta y un cortafuegos distinto. */
export type TestCaseType =
  | "functional"
  | "negative"
  | "boundary"
  | "authorization";

export type TestPriority = "critica" | "alta" | "media" | "baja";
export type AutomationHint = "api" | "ui" | "manual";
export type DataKind = "valid" | "invalid" | "boundary";

export type BoundaryKind =
  | "min"
  | "max"
  | "length"
  | "format"
  | "required"
  | "conditional"
  | "date_order"
  | "enum"
  | "unique";

/** De dónde sale el límite de un caso de borde. `ef_text` exige cita verbatim. */
export type AnchorSource = "ef_text" | "api_field";

export type CoverageStatus = "covered" | "uncovered" | "not_testable";

export interface QaSourceRef {
  scrum_job_id: string;
  scrum_artifact_hash: string;
  scrum_schema_version?: string;
  ef_job_id: string;
  ef_artifact_hash: string;
  ef_schema_version?: string;
  api_job_id?: string | null;
  api_artifact_hash?: string | null;
  api_schema_version?: string | null;
  /** Sin contrato de API no hay casos de autorización, y el motivo se escribe. */
  api_available: boolean;
  api_absent_reason?: string | null;
  ready_snapshot: boolean;
}

export interface QaTarget {
  coverage_threshold: number;
  max_cases_per_criterion: number;
  minutes_by_type: Record<string, number>;
  priority_factor: Record<string, number>;
  manual_capacity_minutes?: number | null;
}

export interface TestStep {
  number: number;
  action: string;
  expected?: string | null;
}

export interface TestDatum {
  name: string;
  value: string;
  kind: DataKind;
  field_ref?: string | null;
  entity_ref?: string | null;
  note?: string | null;
}

export interface BoundaryAnchor {
  rule_ref?: string | null;
  kind: BoundaryKind;
  operator?: string | null;
  value?: string | null;
  anchor_source: AnchorSource;
  /** Cita verbatim del EF. Sin ella, el límite sería una invención. */
  evidence?: string | null;
  api_field_ref?: string | null;
}

export interface AuthCase {
  auth_rule_ref: string;
  endpoint_ref: string;
  actor_ref?: string | null;
  scope: AuthScope;
  expected_status: number;
  negative: boolean;
  scope_column_refs: string[];
}

export interface TestCase {
  id: string;
  title: string;
  story_ref: string;
  /** Criterio de origen. Obligatorio: es el cortafuegos anti-invención. */
  criterion_ref: string;
  epic_ref?: string | null;
  type: TestCaseType;
  preconditions: string[];
  steps: TestStep[];
  test_data: TestDatum[];
  expected_result: string;
  priority: TestPriority;
  automation_hint: AutomationHint;
  estimated_minutes: number;
  boundary?: BoundaryAnchor | null;
  auth_context?: AuthCase | null;
  tags: string[];
  source_refs: string[];
  confidence?: number | null;
  origin?: Origin | null;
}

export interface TraceRow {
  requirement_refs: string[];
  story_ref: string;
  criterion_ref: string;
  story_priority?: MoscowPriority | null;
  test_case_ids: string[];
  status: CoverageStatus;
  question_ref?: string | null;
}

export interface QaCoverage {
  criteria_total: number;
  criteria_covered: number;
  criteria_ratio: number;
  uncovered_criterion_refs: string[];
  not_testable_criterion_refs: string[];
  /** Cobertura de historias must/should: la que entra en el semáforo. */
  blocking_criteria_total: number;
  blocking_criteria_covered: number;
  stories_total: number;
  stories_covered: number;
  uncovered_story_refs: string[];
  requirements_total: number;
  requirements_covered: number;
  uncovered_requirement_refs: string[];
}

export interface TraceMatrix {
  rows: TraceRow[];
  coverage: QaCoverage;
  orphan_criterion_refs: string[];
}

export interface DatasetRow {
  id: string;
  kind: DataKind;
  values: Record<string, string>;
  expectation: string;
  field_refs: string[];
  anchor?: BoundaryAnchor | null;
}

export interface Dataset {
  id: string;
  name: string;
  entity_ref?: string | null;
  description?: string | null;
  rows: DatasetRow[];
  source_refs: string[];
  confidence?: number | null;
  origin?: Origin | null;
}

export interface Suite {
  id: string;
  name: string;
  epic_ref?: string | null;
  test_case_ids: string[];
  estimated_minutes: number;
  depends_on_suite_ids: string[];
}

export interface ExecutionTotals {
  cases_total: number;
  manual_minutes: number;
  by_type: Record<string, number>;
  by_priority: Record<string, number>;
  estimated_sessions?: number | null;
}

export interface ExecutionPlan {
  suites: Suite[];
  /** Orden topológico de ejecución. */
  order: string[];
  /** Ciclos detectados: se reportan, no rompen el plan. */
  dependency_cycles: string[][];
  totals: ExecutionTotals;
}

export interface QaQuestion {
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

export interface QaRisk {
  id: string;
  description: string;
  severity: RiskSeverity;
  mitigation?: string | null;
  source_ref?: string | null;
  confidence?: number | null;
  origin?: Origin | null;
}

export interface QaObservation {
  id: string;
  description: string;
  reason?: string | null;
}

export interface QaAnalysis {
  risks: QaRisk[];
  observations: QaObservation[];
  coverage: QaCoverage;
}

export interface QaMetrics {
  tokens: { input: number; output: number; total: number };
  cost: number;
  duration: number;
  test_cases_total: number;
  datasets_total: number;
  suites_total: number;
  questions_total: number;
  blocking_questions_total: number;
  manual_minutes: number;
  coverage: number;
  /** Casos podados por el techo por criterio. Cada poda deja su Observation. */
  pruned_cases: number;
  skipped: { ref: string; stage: string; reason: string }[];
}

export interface QaArtifact {
  schema_version: string;
  source: QaSourceRef;
  target: QaTarget;
  test_cases: TestCase[];
  trace_matrix: TraceMatrix;
  datasets: Dataset[];
  execution_plan: ExecutionPlan;
  questions_for_qa_lead: QaQuestion[];
  analysis: QaAnalysis;
  metrics: QaMetrics;
}

// --- Respuestas de la API -----------------------------------------------------

export interface TestPlanResult {
  job_id: string;
  status: JobStatus;
  input_job_id: string;
}

export interface QaJobDetail {
  job_id: string;
  status: JobStatus;
  parent_job_id?: string | null;
  input_job_id?: string | null;
  error?: string | null;
  metrics?: Record<string, unknown> | null;
}

export interface QaJobListItem {
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

export interface QaJobList {
  total: number;
  limit: number;
  offset: number;
  estado: JobStatusGroup;
  status_counts: JobStatusCounts;
  items: QaJobListItem[];
}

export interface AvailableScrumJob {
  job_id: string;
  title?: string | null;
  status: JobStatus;
  ready_for_next_stage: boolean;
  blocking_pending: string[];
}

/** Contrato de API de la MISMA cadena del plan Scrum elegido (QA-D1). */
export interface CompatibleApiJob {
  job_id: string;
  title?: string | null;
  status: JobStatus;
  version: number;
  ready_for_next_stage: boolean;
}

export interface QaValidationSummary {
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

/** Export CSV: el mismo contenido como filas (para la UI) y como archivo. */
export interface QaCsvExport {
  kind: "casos" | "trazabilidad";
  rows_total: number;
  filename: string;
  content: string;
  rows: Record<string, string>[];
}
