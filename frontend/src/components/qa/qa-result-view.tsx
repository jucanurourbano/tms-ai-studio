"use client";

// CENTRO DE COMANDO del plan de pruebas. Mismo patrón que EF, Scrum,
// Arquitectura, BD y API: cabecera + grid de tarjetas-sección, contenido en el
// panel lateral universal y PDF como documento lineal.
//
// Lo propio de esta vista son tres cosas:
//
// · La **matriz de trazabilidad**, su visual insignia: criterio × tipo de caso,
//   con el hueco visible y separado por si bloquea el semáforo o solo avisa.
// · Los **badges por tipo de caso**, con vocabulario único en
//   `lib/test-case-kind.ts`. No son decoración: cada tipo tiene una fuente
//   distinta, y el badge es lo que permite ver de un vistazo si un plan es todo
//   camino feliz —el defecto clásico de un plan de pruebas escrito con prisa—.
// · Los **exports CSV**, que salen del backend con BOM y `;` para que Excel los
//   abra de un doble clic. El plan se ejecuta en una hoja de cálculo, no aquí.
//
// Un caso de borde muestra SIEMPRE su cita verbatim: es lo que permite a quien lo
// ejecuta comprobar que la frontera existe de verdad y no la inventó el modelo.

import {
  AlertTriangle,
  ClipboardList,
  Clock,
  Coins,
  Database,
  DollarSign,
  Download,
  Eye,
  FileSpreadsheet,
  Grid3x3,
  ListChecks,
  MessagesSquare,
  Printer,
  ShieldCheck,
  Sigma,
  Target,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { ArtifactNavProvider } from "@/components/artifact/artifact-nav";
import {
  ArtifactPanel,
  type HubSection,
} from "@/components/artifact/artifact-panel";
import { ArtifactPrintDoc } from "@/components/artifact/artifact-print-doc";
import { ArtifactSkeleton } from "@/components/artifact/artifact-skeleton";
import {
  FocusedQuestionFlow,
  type SheetQuestion,
} from "@/components/artifact/focused-questions";
import {
  ActionGroup,
  HeaderActions,
  HUB_WIDTH,
  HubCard,
  HubGrid,
  HubHint,
} from "@/components/artifact/hub-card";
import {
  DataList,
  DataRow,
  EmptyHint,
  GroupLabel,
  IdTag,
  PrintCover,
  PrintFooter,
  RefChip,
  Stat,
  StatRow,
} from "@/components/artifact/primitives";
import { ValidationHint } from "@/components/artifact/validation-controls";
import {
  huecosBloqueantes,
  KindChip,
  TraceMatrixView,
} from "@/components/qa/trace-matrix";
import { QaLeadValidationControls } from "@/components/qa/validation-controls";
import { ConfidenceBadge, JobStatusBadge, Mono } from "@/components/ef/badges";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { qaApi } from "@/lib/api/qa";
import { ApiError } from "@/lib/api/client";
import { makeRefResolver } from "@/lib/artifact-refs";
import { filterByQuery, plural } from "@/lib/artifact-search";
import { useAuth } from "@/lib/auth/auth-context";
import { QA_REF_ROUTES } from "@/lib/qa-refs";
import {
  COVERAGE_STATUS,
  formatMinutes,
  TEST_CASE_KIND,
  TEST_CASE_KIND_ORDER,
  TEST_PRIORITY,
} from "@/lib/test-case-kind";
import type { RiskSeverity } from "@/lib/types/arquitectura";
import type { QuestionStatus } from "@/lib/types/ef";
import type {
  Dataset,
  QaArtifact,
  QaJobDetail,
  QaValidationSummary,
  TestCase,
  TestCaseType,
} from "@/lib/types/qa";
import { useArtifactHub } from "@/lib/use-artifact-hub";
import { useCelebrateOnTrue } from "@/lib/use-celebrate-on-true";
import { usePrintExpand } from "@/lib/use-print-expand";
import { cn } from "@/lib/utils";

const SEVERITY_STYLE: Record<RiskSeverity, string> = {
  alta: "border-red-300 bg-red-50 text-red-700",
  media: "border-amber-300 bg-amber-50 text-amber-700",
  baja: "border-slate-300 bg-slate-50 text-slate-600",
};

const AUTOMATION_LABEL: Record<string, string> = {
  api: "automatizable por API",
  ui: "automatizable por UI",
  manual: "manual",
};

const DATA_KIND_LABEL: Record<string, string> = {
  valid: "válido",
  invalid: "inválido",
  boundary: "frontera",
};

const BOUNDARY_KIND_LABEL: Record<string, string> = {
  min: "mínimo",
  max: "máximo",
  length: "longitud",
  format: "formato",
  required: "obligatorio",
  conditional: "obligatorio condicional",
  date_order: "orden de fechas",
  enum: "conjunto cerrado",
  unique: "unicidad",
};

const SECTION_IDS = [
  "casos",
  "trazabilidad",
  "plan",
  "datasets",
  "resumen",
  "analisis",
  "preguntas",
] as const;

/**
 * Etiqueta de un tipo de caso venido como clave suelta (`target.minutes_by_type`).
 * Si el backend añadiera un tipo, se muestra su clave cruda en vez de un hueco.
 */
function etiquetaDeTipo(key: string): string {
  return key in TEST_CASE_KIND
    ? TEST_CASE_KIND[key as TestCaseType].label
    : key;
}

function download(content: string, filename: string, type: string) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function QaResultView({ job }: { job: QaJobDetail }) {
  const router = useRouter();
  const [artifact, setArtifact] = useState<QaArtifact | null>(null);
  const [summary, setSummary] = useState<QaValidationSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refining, setRefining] = useState(false);
  const [questionMode, setQuestionMode] = useState<"lista" | "enfocado" | null>(
    null,
  );

  const hub = useArtifactHub(SECTION_IDS);
  const { printMode, printNow } = usePrintExpand();
  // Modo lectura: con acceso de solo lectura al módulo «qa» se muestra todo el
  // contenido pero se retiran las acciones de escritura. El backend las
  // rechazaría con 403.
  const { can } = useAuth();
  const puedeEditar = can("qa", "full");
  const celebrate = useCelebrateOnTrue(
    summary?.ready_for_next_stage ?? false,
    summary != null,
  );

  const loadAll = useCallback(() => {
    Promise.all([
      qaApi.getArtifact(job.job_id),
      qaApi.getValidationSummary(job.job_id),
    ])
      .then(([a, s]) => {
        setArtifact(a);
        setSummary(s);
        setError(null);
      })
      .catch((err) =>
        setError(
          err instanceof ApiError
            ? err.message
            : "No se pudo cargar el plan de pruebas.",
        ),
      )
      .finally(() => setLoading(false));
  }, [job.job_id]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const reloadSummary =
    useCallback(async (): Promise<QaValidationSummary | null> => {
      try {
        const s = await qaApi.getValidationSummary(job.job_id);
        setSummary(s);
        return s;
      } catch {
        return null;
      }
    }, [job.job_id]);

  const statusOf = useCallback(
    (id: string): QuestionStatus =>
      summary?.validations.find((x) => x.target_id === id)?.status ??
      "pendiente",
    [summary],
  );
  const respuestaOf = useCallback(
    (id: string): string | null | undefined =>
      summary?.validations.find((x) => x.target_id === id)?.respuesta,
    [summary],
  );

  const answered = useMemo(
    () =>
      summary?.validations.filter((v) => v.status !== "pendiente").length ?? 0,
    [summary],
  );

  const resolveRef = useMemo(() => makeRefResolver(QA_REF_ROUTES), []);
  const canNavigateToRef = useCallback(
    (refId: string) => resolveRef(refId) !== null,
    [resolveRef],
  );
  const navigateToRef = useCallback(
    (refId: string) => {
      const target = resolveRef(refId);
      if (!target) {
        toast.info(
          `${refId} pertenece a las fuentes (EF, plan Scrum o contrato de API), no a este plan de pruebas.`,
        );
        return;
      }
      if (target.sectionId === "preguntas") setQuestionMode("lista");
      hub.pushEntry({ ...target, refId });
    },
    [resolveRef, hub],
  );

  const openQuestions = useCallback(() => {
    setQuestionMode(null);
    hub.openSection("preguntas");
  }, [hub]);

  const doRefine = useCallback(async () => {
    setRefining(true);
    try {
      const child = await qaApi.refine(job.job_id);
      toast.success("Plan de pruebas afinado en curso");
      router.push(`/agents/qa/jobs/${child.job_id}`);
    } catch (err) {
      toast.error("No se pudo regenerar", {
        description: err instanceof ApiError ? err.message : undefined,
      });
    } finally {
      setRefining(false);
    }
  }, [job.job_id, router]);

  const descargarCsv = useCallback(
    async (cual: "casos" | "matriz") => {
      try {
        const data = await qaApi.exportCsv(job.job_id, cual);
        // El contenido llega con BOM desde el backend; el Blob lo conserva, que
        // es lo único que le dice a Excel que el archivo es UTF-8.
        download(data.content, data.filename, "text/csv;charset=utf-8");
      } catch (err) {
        toast.error("No se pudo generar el CSV", {
          description: err instanceof ApiError ? err.message : undefined,
        });
      }
    },
    [job.job_id],
  );

  if (loading) return <ArtifactSkeleton />;
  if (error || !artifact) {
    return (
      <div className="p-6 text-sm text-red-600">
        {error ?? "No se pudo cargar el plan de pruebas."}
      </div>
    );
  }

  const a = artifact;
  const ready = summary?.ready_for_next_stage ?? false;
  const blockingRemaining = summary?.blocking_pending.length ?? 0;
  const canRefine = answered > 0;

  const filas = a.trace_matrix.rows;
  const huecosQueBloquean = huecosBloqueantes(filas);
  const cobertura = a.trace_matrix.coverage;
  const totales = a.execution_plan.totals;
  const ciclos = a.execution_plan.dependency_cycles;
  const sinContrato = !a.source.api_available;
  const casosAuth = a.test_cases.filter((c) => c.type === "authorization");
  const soloCaminoFeliz =
    a.test_cases.length > 0 &&
    a.test_cases.every((c) => c.type === "functional");

  const casoDe = (id: string) => a.test_cases.find((c) => c.id === id);

  const questions: SheetQuestion[] = a.questions_for_qa_lead.map((q) => ({
    id: q.id,
    question: q.question,
    reason: q.reason,
    blocking: q.blocking,
    linked_to_ref: q.linked_to_ref,
  }));

  const renderCasos = (lista: TestCase[], query: string) => {
    const items = filterByQuery(query, lista, (c) => [
      c.id,
      c.title,
      c.expected_result,
      c.criterion_ref,
      c.story_ref,
      ...c.steps.map((s) => s.action),
    ]);
    if (items.length === 0) return <EmptyHint>Sin coincidencias.</EmptyHint>;
    return (
      <DataList>
        {items.map((c) => (
          <TestCaseBlock key={c.id} testCase={c} />
        ))}
      </DataList>
    );
  };

  const contarCasos = (lista: TestCase[]) => (query: string) =>
    filterByQuery(query, lista, (c) => [
      c.id,
      c.title,
      c.expected_result,
      c.criterion_ref,
      c.story_ref,
      ...c.steps.map((s) => s.action),
    ]).length;

  // Con el semáforo en rojo, el paso siguiente es regenerar; en verde, el plan
  // ya se puede ejecutar y el panel se cierra solo.
  const nextStepAction =
    puedeEditar && !ready && canRefine
      ? {
          label: "Regenerar plan afinado",
          onClick: () => void doRefine(),
          hint: "Reinyecta tus respuestas y genera una versión afinada.",
        }
      : undefined;

  const sections: HubSection[] = [
    {
      id: "casos",
      title: "Casos de prueba",
      printTitle: "Catálogo de casos de prueba",
      icon: <ClipboardList />,
      count: a.test_cases.length,
      tone: "amber",
      pattern: "lines",
      stat: {
        value: a.test_cases.length,
        label: plural(a.test_cases.length, "caso"),
      },
      insight: (
        <>
          {TEST_CASE_KIND_ORDER.filter(
            (t) => a.test_cases.some((c) => c.type === t),
          )
            .map(
              (t) =>
                `${a.test_cases.filter((c) => c.type === t).length} ${TEST_CASE_KIND[
                  t
                ].label.toLowerCase()}`,
            )
            .join(" · ")}
          {sinContrato && (
            <>
              {" "}
              ·{" "}
              <span className="text-amber-700">sin casos de autorización</span>
            </>
          )}
        </>
      ),
      urgent: soloCaminoFeliz,
      urgentLabel: "solo camino feliz",
      tabs: [
        {
          id: "todos",
          label: "Todos",
          count: a.test_cases.length,
          matchCount: contarCasos(a.test_cases),
          render: ({ query }) => renderCasos(a.test_cases, query),
        },
        ...TEST_CASE_KIND_ORDER.map((type) => {
          const lista = a.test_cases.filter((c) => c.type === type);
          return {
            id: type,
            label: TEST_CASE_KIND[type].plural,
            count: lista.length,
            matchCount: contarCasos(lista),
            // Cada pestaña es un FILTRO de "Todos": incluirlas en el PDF
            // duplicaría cada caso una vez más.
            printSkip: true,
            render: ({ query }: { query: string }) =>
              lista.length === 0 ? (
                <EmptyHint>
                  {type === "authorization" && sinContrato
                    ? a.source.api_absent_reason ||
                      "No se indicó contrato de API: sin la matriz de autorización, quién puede ver qué sería una suposición."
                    : `Sin casos de tipo ${TEST_CASE_KIND[type].label.toLowerCase()}.`}
                </EmptyHint>
              ) : (
                renderCasos(lista, query)
              ),
          };
        }),
      ],
    },
    {
      id: "trazabilidad",
      title: "Trazabilidad",
      printTitle: "Matriz de trazabilidad",
      icon: <Grid3x3 />,
      count: filas.length,
      searchable: false,
      tone: "violet",
      pattern: "dots",
      stat: {
        value: `${Math.round(cobertura.criteria_ratio * 100)}%`,
        label: "criterios cubiertos",
      },
      insight:
        huecosQueBloquean.length > 0 ? (
          <span className="text-red-700">
            {huecosQueBloquean.length} criterio(s) must/should sin cubrir
          </span>
        ) : (
          <>
            {cobertura.criteria_covered}/{cobertura.criteria_total} criterios ·{" "}
            {cobertura.requirements_covered}/{cobertura.requirements_total}{" "}
            requisitos
          </>
        ),
      urgent: huecosQueBloquean.length > 0,
      urgentLabel: `${huecosQueBloquean.length} sin cubrir`,
      actions: (
        <Button
          variant="outline"
          size="sm"
          className="gap-1.5 print:hidden"
          onClick={() => void descargarCsv("matriz")}
        >
          <FileSpreadsheet className="h-3.5 w-3.5" />
          CSV
        </Button>
      ),
      render: ({ refId }) => (
        <TraceMatrixView
          rows={filas}
          cases={a.test_cases}
          highlightId={refId}
        />
      ),
    },
    {
      id: "plan",
      title: "Plan de ejecución",
      icon: <ListChecks />,
      count: a.execution_plan.suites.length,
      searchable: false,
      tone: "sky",
      pattern: "lines",
      stat: {
        value: formatMinutes(totales.manual_minutes),
        label: "esfuerzo manual",
      },
      insight:
        ciclos.length > 0 ? (
          <span className="text-red-700">
            {ciclos.length} ciclo(s) de dependencias entre suites
          </span>
        ) : (
          <>
            {a.execution_plan.suites.length} suites en orden topológico
            {totales.estimated_sessions != null && (
              <> · {totales.estimated_sessions} sesión(es)</>
            )}
          </>
        ),
      urgent: ciclos.length > 0,
      urgentLabel: `${ciclos.length} ciclos`,
      render: () => (
        <ExecutionPlanBlock artifact={a} casoDe={casoDe} />
      ),
    },
    {
      id: "datasets",
      title: "Datasets",
      printTitle: "Datos de prueba",
      icon: <Database />,
      count: a.datasets.length,
      tone: "emerald",
      pattern: "dots",
      stat: {
        value: a.datasets.reduce((n, d) => n + d.rows.length, 0),
        label: "filas de datos",
      },
      insight: (
        <>
          {a.datasets.length} conjunto(s) reutilizables · válidos, inválidos y de
          frontera
        </>
      ),
      render: ({ query }) => {
        const items = filterByQuery(query, a.datasets, (d) => [
          d.name,
          d.description ?? "",
          ...d.rows.flatMap((r) => Object.values(r.values)),
        ]);
        if (items.length === 0)
          return <EmptyHint>Sin datasets que mostrar.</EmptyHint>;
        return (
          <DataList>
            {items.map((d) => (
              <DatasetBlock key={d.id} dataset={d} />
            ))}
          </DataList>
        );
      },
    },
    {
      id: "resumen",
      title: "Resumen del plan",
      printTitle: "Configuración efectiva y fuentes",
      icon: <Sigma />,
      searchable: false,
      tone: "teal",
      pattern: "dots",
      stat: {
        value: `${Math.round(a.target.coverage_threshold * 100)}%`,
        label: "cobertura exigida",
      },
      insight: sinContrato ? (
        <span className="text-amber-700">
          Sin contrato de API: no hay casos de autorización
        </span>
      ) : (
        <>
          Contrato de API vinculado · techo de {a.target.max_cases_per_criterion}{" "}
          casos por criterio
        </>
      ),
      render: () => <ResumenBlock artifact={a} />,
    },
    {
      id: "analisis",
      title: "Análisis",
      icon: <Target />,
      tone: "rose",
      pattern: "waves",
      stat: {
        value: `${Math.round(a.metrics.coverage * 100)}%`,
        label: "cobertura",
      },
      insight: (
        <>
          {a.analysis.risks.length} riesgos ·{" "}
          {a.analysis.observations.length} observaciones
          {a.metrics.pruned_cases > 0 && (
            <> · {a.metrics.pruned_cases} casos podados</>
          )}
        </>
      ),
      urgent: a.analysis.risks.some((r) => r.severity === "alta"),
      urgentLabel: "riesgo alto",
      tabs: [
        {
          id: "riesgos",
          label: "Riesgos",
          count: a.analysis.risks.length,
          render: ({ query }) => {
            const items = filterByQuery(query, a.analysis.risks, (r) => [
              r.description,
              r.mitigation ?? "",
            ]);
            if (items.length === 0)
              return <EmptyHint>Sin riesgos señalados.</EmptyHint>;
            return (
              <DataList>
                {items.map((r) => (
                  <DataRow key={r.id} id={r.id}>
                    <div className="space-y-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <IdTag id={r.id} />
                        <Badge
                          variant="outline"
                          className={SEVERITY_STYLE[r.severity]}
                        >
                          {r.severity}
                        </Badge>
                        {r.source_ref && <RefChip refId={r.source_ref} />}
                      </div>
                      <p className="text-xs">{r.description}</p>
                      {r.mitigation && (
                        <p className="text-xs text-muted-foreground">
                          Mitigación: {r.mitigation}
                        </p>
                      )}
                    </div>
                  </DataRow>
                ))}
              </DataList>
            );
          },
        },
        {
          id: "cobertura",
          label: "Cobertura",
          render: () => <CoberturaBlock artifact={a} />,
        },
        {
          id: "observaciones",
          label: "Observaciones",
          count: a.analysis.observations.length,
          render: ({ query }) => {
            const items = filterByQuery(query, a.analysis.observations, (o) => [
              o.description,
              o.reason ?? "",
            ]);
            if (items.length === 0)
              return <EmptyHint>Sin observaciones.</EmptyHint>;
            return (
              <DataList>
                {items.map((o) => (
                  <DataRow key={o.id} id={o.id}>
                    <div className="space-y-0.5">
                      <p className="text-xs">{o.description}</p>
                      {o.reason && (
                        <p className="text-xs text-muted-foreground">
                          {o.reason}
                        </p>
                      )}
                    </div>
                  </DataRow>
                ))}
              </DataList>
            );
          },
        },
      ],
    },
    {
      id: "preguntas",
      title: "Preguntas",
      printTitle: "Preguntas al QA lead",
      icon: <MessagesSquare />,
      count: a.questions_for_qa_lead.length,
      tone: "amber",
      pattern: "waves",
      stat: { value: blockingRemaining, label: "bloqueantes pendientes" },
      insight:
        blockingRemaining > 0 ? (
          <span className="text-red-700">
            El plan no se puede ejecutar hasta responderlas
          </span>
        ) : (
          <>{answered} respondidas</>
        ),
      urgent: blockingRemaining > 0,
      urgentLabel: `${blockingRemaining} bloqueantes`,
      render: ({ query, forPrint }) => {
        const items = filterByQuery(query, questions, (q) => [
          q.question,
          q.reason,
        ]);
        if (items.length === 0)
          return <EmptyHint>Sin preguntas pendientes.</EmptyHint>;

        const modo =
          questionMode ??
          (items.some((q) => q.blocking && statusOf(q.id) === "pendiente") &&
          !forPrint
            ? "enfocado"
            : "lista");

        if (modo === "enfocado" && !forPrint) {
          return (
            <FocusedQuestionFlow
              questions={items}
              statusOf={statusOf}
              ready={ready}
              readyLabel="El plan de pruebas se puede ejecutar"
              nextAction={nextStepAction}
              onClose={hub.close}
              renderControls={(q, onAnswered) => (
                <QaLeadValidationControls
                  jobId={job.job_id}
                  targetId={q.id}
                  status={statusOf(q.id)}
                  respuesta={respuestaOf(q.id)}
                  readOnly={!puedeEditar}
                  onChanged={() => {
                    void reloadSummary();
                    onAnswered();
                  }}
                />
              )}
            />
          );
        }

        return (
          <div className="space-y-3">
            {!forPrint && (
              <div className="flex items-center justify-between print:hidden">
                <ValidationHint />
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setQuestionMode("enfocado")}
                >
                  Modo enfocado
                </Button>
              </div>
            )}
            <DataList>
              {items.map((q) => (
                <DataRow key={q.id} id={q.id}>
                  <div className="space-y-1.5">
                    <div className="flex flex-wrap items-center gap-2">
                      <IdTag id={q.id} />
                      {q.blocking && (
                        <Badge
                          variant="outline"
                          className="border-red-300 bg-red-50 text-red-700"
                        >
                          bloqueante
                        </Badge>
                      )}
                      {q.linked_to_ref && <RefChip refId={q.linked_to_ref} />}
                    </div>
                    <p className="text-sm font-medium">{q.question}</p>
                    <p className="text-xs text-muted-foreground">{q.reason}</p>
                    <QaLeadValidationControls
                      jobId={job.job_id}
                      targetId={q.id}
                      status={statusOf(q.id)}
                      respuesta={respuestaOf(q.id)}
                      readOnly={!puedeEditar}
                      onChanged={() => void reloadSummary()}
                    />
                  </div>
                </DataRow>
              ))}
            </DataList>
          </div>
        );
      },
    },
  ];

  return (
    <ArtifactNavProvider
      navigateToRef={navigateToRef}
      canNavigateToRef={canNavigateToRef}
    >
      <div className="flex h-full flex-col">
        <PrintCover
          kind="Plan de pruebas"
          title={`${a.test_cases.length} casos · ${Math.round(
            cobertura.criteria_ratio * 100,
          )}% de criterios cubiertos`}
          subtitle="Casos por tipo, matriz de trazabilidad requisito → historia → criterio → caso, datos de prueba, plan de ejecución y preguntas al QA lead."
          version="1.0.0"
          stats={[
            { label: "casos", value: String(a.test_cases.length) },
            { label: "criterios", value: String(cobertura.criteria_total) },
            {
              label: "esfuerzo manual",
              value: formatMinutes(totales.manual_minutes),
            },
            {
              label: "cobertura",
              value: `${Math.round(a.metrics.coverage * 100)}%`,
            },
          ]}
        />
        <PrintFooter title="Plan de pruebas" />

        {/* Barra superior de afinamiento + semáforo */}
        <div className="sticky top-0 z-10 border-b bg-background/95 px-6 py-4 backdrop-blur print:hidden">
          <div className={HUB_WIDTH}>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-2 text-sm">
              <span className="font-heading font-semibold">
                Plan de pruebas v1.0.0
              </span>
              <Badge variant="outline">
                {job.parent_job_id ? "v2 · afinamiento" : "v1 · original"}
              </Badge>
              <Badge variant="outline" className="gap-1">
                <ShieldCheck className="h-3 w-3" />
                {a.test_cases.length} casos · {formatMinutes(
                  totales.manual_minutes,
                )}
              </Badge>
              {sinContrato && (
                <Badge
                  variant="outline"
                  className="border-amber-300 bg-amber-50 text-amber-700"
                  title={
                    a.source.api_absent_reason ??
                    "No se indicó contrato de API al generar el plan"
                  }
                >
                  sin casos de autorización
                </Badge>
              )}
              {job.input_job_id && (
                <Link
                  href={`/agents/scrum/jobs/${job.input_job_id}`}
                  className="text-xs text-muted-foreground underline-offset-2 hover:text-primary hover:underline"
                >
                  plan Scrum (<Mono>{job.input_job_id}</Mono>)
                </Link>
              )}
              {a.source?.api_job_id && (
                <Link
                  href={`/agents/api/jobs/${a.source.api_job_id}`}
                  className="text-xs text-muted-foreground underline-offset-2 hover:text-primary hover:underline"
                >
                  contrato de API (<Mono>{a.source.api_job_id}</Mono>)
                </Link>
              )}
              {a.source?.ef_job_id && (
                <Link
                  href={`/agents/ef/jobs/${a.source.ef_job_id}`}
                  className="text-xs text-muted-foreground underline-offset-2 hover:text-primary hover:underline"
                >
                  EF de origen (<Mono>{a.source.ef_job_id}</Mono>)
                </Link>
              )}
              <span className="text-xs text-muted-foreground">
                {answered} respondidas
              </span>
              <span
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs",
                  ready
                    ? "border-emerald-300 bg-emerald-50 text-emerald-700"
                    : "border-slate-300 bg-slate-50 text-slate-600",
                  ready && celebrate && "animate-celebrate",
                )}
              >
                <span
                  className={cn(
                    "h-2 w-2 rounded-full",
                    ready ? "bg-emerald-500" : "bg-slate-400",
                  )}
                />
                {ready
                  ? "El plan de pruebas se puede ejecutar"
                  : "Pendiente de afinamiento"}
              </span>

              {!puedeEditar && (
                <span
                  className="inline-flex items-center gap-1.5 rounded-full border border-slate-300 bg-slate-50 px-2 py-0.5 text-xs text-slate-600 print:hidden"
                  title="Tu rol permite consultar este módulo, no modificarlo"
                >
                  <Eye className="h-3 w-3" />
                  Modo lectura
                </span>
              )}

              <div className="ml-auto">
                <HeaderActions>
                  {puedeEditar && a.questions_for_qa_lead.length > 0 && (
                    <ActionGroup>
                      <Button
                        variant="outline"
                        size="sm"
                        className="gap-1.5"
                        onClick={openQuestions}
                      >
                        <MessagesSquare className="h-3.5 w-3.5" />
                        Responder preguntas
                        {blockingRemaining > 0 && (
                          <span className="inline-flex min-w-4 items-center justify-center rounded-full bg-red-600 px-1 text-[10px] font-semibold text-white tabular-nums">
                            {blockingRemaining}
                          </span>
                        )}
                      </Button>
                    </ActionGroup>
                  )}
                  <ActionGroup>
                    <Button
                      variant="outline"
                      size="sm"
                      className="gap-1.5"
                      onClick={() => printNow()}
                    >
                      <Printer className="h-3.5 w-3.5" />
                      Exportar PDF
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      className="gap-1.5"
                      onClick={() => void descargarCsv("casos")}
                      title="CSV de los casos, listo para Excel (UTF-8 con BOM, separador ;)"
                    >
                      <FileSpreadsheet className="h-3.5 w-3.5" />
                      Casos CSV
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      className="gap-1.5"
                      onClick={() => void descargarCsv("matriz")}
                      title="CSV de la matriz de trazabilidad, listo para Excel"
                    >
                      <Grid3x3 className="h-3.5 w-3.5" />
                      Matriz CSV
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      className="gap-1.5"
                      onClick={() =>
                        download(
                          JSON.stringify(a, null, 2),
                          `qa-artifact-${job.job_id}.json`,
                          "application/json",
                        )
                      }
                    >
                      <Download className="h-3.5 w-3.5" />
                      JSON
                    </Button>
                  </ActionGroup>
                  {puedeEditar && (
                    <ActionGroup>
                      <Dialog>
                        <DialogTrigger
                          render={
                            <Button size="sm" disabled={!canRefine}>
                              Regenerar plan afinado
                            </Button>
                          }
                        />
                        <DialogContent>
                          <DialogHeader>
                            <DialogTitle>Regenerar plan afinado</DialogTitle>
                            <DialogDescription>
                              Se creará un plan hijo reinyectando tus respuestas
                              y se ejecutará el modelo real.
                            </DialogDescription>
                          </DialogHeader>
                          <div className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800">
                            Costo estimado: ~${a.metrics.cost.toFixed(4)}{" "}
                            (similar al plan anterior). Esta acción consume
                            tokens de la API.
                          </div>
                          <DialogFooter>
                            <Button
                              onClick={doRefine}
                              disabled={refining || !canRefine}
                            >
                              {refining
                                ? "Regenerando…"
                                : "Confirmar y regenerar"}
                            </Button>
                          </DialogFooter>
                        </DialogContent>
                      </Dialog>
                    </ActionGroup>
                  )}
                </HeaderActions>
              </div>
            </div>
          </div>
        </div>

        {/* Mini-stats, con el estado separado a la derecha. */}
        <div className="border-b px-6 py-5 print:hidden">
          <div className={HUB_WIDTH}>
            <div className="flex flex-wrap items-center gap-x-8 gap-y-4">
              <StatRow>
                <Stat
                  icon={<ClipboardList />}
                  value={a.test_cases.length}
                  label="casos"
                />
                <Stat
                  icon={<ShieldCheck />}
                  value={casosAuth.length}
                  label="de autorización"
                />
                <Stat
                  icon={<Grid3x3 />}
                  value={`${cobertura.criteria_covered}/${cobertura.criteria_total}`}
                  label="criterios cubiertos"
                />
                <Stat
                  icon={<Clock />}
                  value={formatMinutes(totales.manual_minutes)}
                  label="esfuerzo manual"
                />
                <Stat
                  icon={<Target />}
                  value={`${Math.round(a.metrics.coverage * 100)}%`}
                  label="cobertura"
                />
                <Stat
                  icon={<Coins />}
                  value={a.metrics.tokens.total.toLocaleString("es-PE")}
                  label="tokens"
                />
                <Stat
                  icon={<DollarSign />}
                  value={`$${a.metrics.cost.toFixed(4)}`}
                  label="costo"
                />
              </StatRow>
              <div className="md:ml-auto md:border-l md:border-border/70 md:pl-8">
                <JobStatusBadge status={job.status} />
              </div>
            </div>
          </div>
        </div>

        {/* EL HUB */}
        <div className="px-4 py-5 md:px-6 print:hidden">
          <HubGrid>
            {sections.map((s, i) => (
              <HubCard
                key={s.id}
                tone={s.tone}
                pattern={s.pattern}
                icon={s.icon}
                title={s.title}
                stat={s.stat}
                metrics={s.metrics}
                insight={s.insight}
                urgent={s.urgent}
                urgentLabel={s.urgentLabel}
                prominent={i < 3}
                onOpen={() =>
                  s.id === "preguntas" ? openQuestions() : hub.openSection(s.id)
                }
              />
            ))}
          </HubGrid>
          <HubHint />
        </div>

        <ArtifactPanel hub={hub} sections={sections} module="qa" />
        <ArtifactPrintDoc sections={sections} active={printMode} />
      </div>
    </ArtifactNavProvider>
  );
}

// --- subcomponentes ----------------------------------------------------------

/** Un caso de prueba completo: pasos, datos, límite citado y trazabilidad. */
function TestCaseBlock({ testCase: c }: { testCase: TestCase }) {
  return (
    <DataRow id={c.id}>
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <IdTag id={c.id} />
          <KindChip type={c.type} />
          <Badge variant="outline" className={TEST_PRIORITY[c.priority].badge}>
            {TEST_PRIORITY[c.priority].label}
          </Badge>
          <span className="text-[11px] text-muted-foreground">
            {AUTOMATION_LABEL[c.automation_hint] ?? c.automation_hint} ·{" "}
            {c.estimated_minutes} min
          </span>
          <ConfidenceBadge value={c.confidence ?? undefined} />
        </div>

        <p className="text-sm font-medium">{c.title}</p>

        <div className="flex flex-wrap items-center gap-1">
          <RefChip refId={c.story_ref} />
          <RefChip refId={c.criterion_ref} />
          {c.epic_ref && <RefChip refId={c.epic_ref} />}
          {c.source_refs.map((ref) => (
            <RefChip key={ref} refId={ref} />
          ))}
        </div>

        {c.preconditions.length > 0 && (
          <p className="text-xs text-muted-foreground">
            <b>Precondiciones:</b> {c.preconditions.join(" · ")}
          </p>
        )}

        <ol className="space-y-0.5 text-xs">
          {c.steps.map((s) => (
            <li key={s.number} className="flex gap-2">
              <span className="shrink-0 font-mono text-muted-foreground">
                {s.number}.
              </span>
              <span>
                {s.action}
                {s.expected && (
                  <span className="text-muted-foreground"> → {s.expected}</span>
                )}
              </span>
            </li>
          ))}
        </ol>

        {c.test_data.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
            {c.test_data.map((d) => (
              <span
                key={`${c.id}-${d.name}`}
                className="rounded border bg-muted/40 px-1.5 py-px font-mono"
                title={`${DATA_KIND_LABEL[d.kind] ?? d.kind}${
                  d.note ? ` · ${d.note}` : ""
                }`}
              >
                {d.name} = {d.value || "∅"}
              </span>
            ))}
          </div>
        )}

        <p className="text-xs">
          <b>Resultado esperado:</b> {c.expected_result}
        </p>

        {c.boundary && (
          <div className="rounded-md border border-sky-200 bg-sky-50/60 p-2 text-xs">
            <p className="font-medium text-sky-800">
              Límite:{" "}
              {BOUNDARY_KIND_LABEL[c.boundary.kind] ?? c.boundary.kind}
              {c.boundary.operator || c.boundary.value ? (
                <>
                  {" "}
                  <Mono>
                    {c.boundary.operator} {c.boundary.value}
                  </Mono>
                </>
              ) : null}
            </p>
            {/* La cita verbatim es el cortafuegos del tipo de caso más
                peligroso: sin la frase, el límite sería una invención que
                pasaría la ejecución certificando algo que nadie dijo. */}
            {c.boundary.evidence && (
              <p className="mt-0.5 italic text-muted-foreground">
                «{c.boundary.evidence}»
              </p>
            )}
            <div className="mt-1 flex flex-wrap items-center gap-1">
              {c.boundary.rule_ref && <RefChip refId={c.boundary.rule_ref} />}
              {c.boundary.api_field_ref && (
                <RefChip refId={c.boundary.api_field_ref} />
              )}
              <span className="text-[10px] text-muted-foreground">
                {c.boundary.anchor_source === "ef_text"
                  ? "extraído del texto del EF"
                  : "campo estructurado del contrato de API"}
              </span>
            </div>
          </div>
        )}

        {c.auth_context && (
          <div className="rounded-md border border-violet-200 bg-violet-50/60 p-2 text-xs">
            <p className="font-medium text-violet-800">
              {c.auth_context.negative ? "Debe rechazar" : "Debe permitir"} ·
              HTTP {c.auth_context.expected_status}
            </p>
            <div className="mt-1 flex flex-wrap items-center gap-1">
              <RefChip refId={c.auth_context.auth_rule_ref} />
              <RefChip refId={c.auth_context.endpoint_ref} />
              {c.auth_context.actor_ref && (
                <RefChip refId={c.auth_context.actor_ref} />
              )}
              {c.auth_context.scope_column_refs.map((ref) => (
                <RefChip key={ref} refId={ref} />
              ))}
            </div>
          </div>
        )}
      </div>
    </DataRow>
  );
}

/** Un dataset con sus filas y qué debe pasar con cada una. */
function DatasetBlock({ dataset: d }: { dataset: Dataset }) {
  const columnas = [...new Set(d.rows.flatMap((r) => Object.keys(r.values)))];
  return (
    <DataRow id={d.id}>
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <IdTag id={d.id} />
          <span className="font-heading text-sm font-semibold">{d.name}</span>
          {d.entity_ref && <RefChip refId={d.entity_ref} />}
          <ConfidenceBadge value={d.confidence ?? undefined} />
        </div>
        {d.description && (
          <p className="text-xs text-muted-foreground">{d.description}</p>
        )}

        {d.rows.length === 0 ? (
          <EmptyHint>Sin filas.</EmptyHint>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[28rem] text-xs">
              <thead>
                <tr className="border-b text-left text-muted-foreground">
                  <th className="py-1 pr-3 font-medium">Fila</th>
                  {columnas.map((col) => (
                    <th key={col} className="py-1 pr-3 font-medium">
                      {col}
                    </th>
                  ))}
                  <th className="py-1 font-medium">Qué debe pasar</th>
                </tr>
              </thead>
              <tbody>
                {d.rows.map((r) => (
                  <tr key={r.id} className="border-b border-border/50 align-top">
                    <td className="py-1 pr-3">
                      <span className="flex items-center gap-1.5">
                        <Mono>{r.id}</Mono>
                        <span
                          className={cn(
                            "rounded px-1 py-px text-[10px]",
                            r.kind === "valid" &&
                              "bg-emerald-100 text-emerald-700",
                            r.kind === "invalid" &&
                              "bg-orange-100 text-orange-700",
                            r.kind === "boundary" && "bg-sky-100 text-sky-700",
                          )}
                        >
                          {DATA_KIND_LABEL[r.kind] ?? r.kind}
                        </span>
                      </span>
                    </td>
                    {columnas.map((col) => (
                      <td key={col} className="py-1 pr-3 font-mono">
                        {r.values[col] === undefined ? (
                          <span className="text-muted-foreground/50">—</span>
                        ) : r.values[col] === "" ? (
                          <span className="text-muted-foreground">∅</span>
                        ) : (
                          r.values[col]
                        )}
                      </td>
                    ))}
                    <td className="py-1">
                      {r.expectation}
                      {r.anchor?.evidence && (
                        <span className="block italic text-muted-foreground">
                          «{r.anchor.evidence}»
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </DataRow>
  );
}

/** Suites en orden de ejecución, con su esfuerzo y sus dependencias. */
function ExecutionPlanBlock({
  artifact: a,
  casoDe,
}: {
  artifact: QaArtifact;
  casoDe: (id: string) => TestCase | undefined;
}) {
  const plan = a.execution_plan;
  const ordenadas = plan.order
    .map((id) => plan.suites.find((s) => s.id === id))
    .filter((s): s is NonNullable<typeof s> => s != null);
  // Una suite que no aparece en el orden no debe desaparecer de la vista: se
  // muestra al final, porque omitirla haría creer que el plan la cubre.
  const sueltas = plan.suites.filter((s) => !plan.order.includes(s.id));

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-1 text-xs">
        <span>
          <b>{plan.totals.cases_total}</b> casos
        </span>
        <span>
          <b>{formatMinutes(plan.totals.manual_minutes)}</b> de ejecución manual
        </span>
        {a.target.manual_capacity_minutes != null && (
          <span>
            capacidad declarada:{" "}
            {formatMinutes(a.target.manual_capacity_minutes)}
            {plan.totals.estimated_sessions != null && (
              <> · {plan.totals.estimated_sessions} sesión(es)</>
            )}
          </span>
        )}
      </div>

      <p className="text-[11px] text-muted-foreground">
        Los minutos salen de una tabla por tipo y prioridad guardada en el
        artefacto, no de una estimación del modelo: dos corridas del mismo plan
        dan el mismo número (QA-D8).
      </p>

      {plan.dependency_cycles.length > 0 && (
        <div className="rounded-lg border border-red-200 bg-red-50/60 p-2.5 text-xs">
          <p className="flex items-center gap-1.5 font-medium text-red-700">
            <AlertTriangle className="h-3.5 w-3.5" />
            Ciclos de dependencias entre suites
          </p>
          {plan.dependency_cycles.map((ciclo) => (
            <p key={ciclo.join("-")} className="mt-0.5 font-mono">
              {ciclo.join(" → ")} → {ciclo[0]}
            </p>
          ))}
          <p className="mt-0.5 text-muted-foreground">
            El orden topológico no es completo mientras existan: hay que romper
            la dependencia circular en el plan Scrum.
          </p>
        </div>
      )}

      <DataList>
        {[...ordenadas, ...sueltas].map((s, i) => (
          <DataRow key={s.id} id={s.id}>
            <div className="space-y-1.5">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-[11px] text-muted-foreground">
                  {i < ordenadas.length ? `#${i + 1}` : "sin orden"}
                </span>
                <IdTag id={s.id} />
                <span className="font-heading text-sm font-semibold">
                  {s.name}
                </span>
                {s.epic_ref && <RefChip refId={s.epic_ref} />}
                <Badge variant="outline">
                  {formatMinutes(s.estimated_minutes)}
                </Badge>
              </div>
              {s.depends_on_suite_ids.length > 0 && (
                <p className="text-xs text-muted-foreground">
                  Depende de: {s.depends_on_suite_ids.join(", ")}
                </p>
              )}
              <div className="flex flex-wrap items-center gap-1">
                {s.test_case_ids.map((id) => {
                  const c = casoDe(id);
                  return (
                    <span
                      key={id}
                      className={cn(
                        "rounded px-1.5 py-px font-mono text-[10px] ring-1",
                        c
                          ? TEST_CASE_KIND[c.type].badge
                          : "bg-slate-100 text-slate-600 ring-slate-200",
                      )}
                      title={c?.title ?? "Caso no encontrado en el artefacto"}
                    >
                      {id}
                    </span>
                  );
                })}
              </div>
            </div>
          </DataRow>
        ))}
      </DataList>
    </div>
  );
}

/** Configuración efectiva de la corrida y las fuentes de las que salió. */
function ResumenBlock({ artifact: a }: { artifact: QaArtifact }) {
  const t = a.target;
  const filas: [string, string][] = [
    ["Cobertura exigida", `${Math.round(t.coverage_threshold * 100)}%`],
    ["Techo de casos por criterio", String(t.max_cases_per_criterion)],
    [
      "Minutos por tipo",
      Object.entries(t.minutes_by_type)
        .map(([k, v]) => `${etiquetaDeTipo(k)}: ${v}`)
        .join(" · "),
    ],
    [
      "Factor por prioridad",
      Object.entries(t.priority_factor)
        .map(([k, v]) => `${k}: ×${v}`)
        .join(" · "),
    ],
    [
      "Capacidad de QA",
      t.manual_capacity_minutes != null
        ? formatMinutes(t.manual_capacity_minutes)
        : "no declarada",
    ],
  ];

  return (
    <div className="space-y-3">
      <table className="w-full text-xs">
        <tbody>
          {filas.map(([k, v]) => (
            <tr key={k} className="border-b border-border/50">
              <td className="py-1.5 pr-4 text-muted-foreground">{k}</td>
              <td className="py-1.5 font-medium">{v}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <p className="text-[11px] text-muted-foreground">
        Los umbrales se guardan en el artefacto para que el cálculo sea
        auditable: se puede recomputar la cobertura y el esfuerzo y obtener los
        mismos números, sin adivinar con qué parámetros se generó.
      </p>

      <GroupLabel>Fuentes</GroupLabel>
      <div className="space-y-1 text-xs">
        <p>
          Plan Scrum <Mono>{a.source.scrum_job_id}</Mono>{" "}
          <span className="text-muted-foreground">
            ({a.source.scrum_artifact_hash})
          </span>
        </p>
        <p>
          EF <Mono>{a.source.ef_job_id}</Mono>{" "}
          <span className="text-muted-foreground">
            ({a.source.ef_artifact_hash})
          </span>
        </p>
        {a.source.api_available ? (
          <p>
            Contrato de API <Mono>{a.source.api_job_id}</Mono>{" "}
            <span className="text-muted-foreground">
              ({a.source.api_artifact_hash})
            </span>
          </p>
        ) : (
          // La ausencia se declara, no se disimula: sin esto, "no se diseñaron
          // casos de autorización" y "no se pudo diseñarlos" serían iguales al
          // leer el plan.
          <p className="text-amber-700">
            Sin contrato de API ·{" "}
            {a.source.api_absent_reason ?? "no se indicó ninguno"}
          </p>
        )}
      </div>

      {a.metrics.pruned_cases > 0 && (
        <p className="text-xs text-amber-700">
          {a.metrics.pruned_cases} caso(s) podados por el techo por criterio.
          Cada poda dejó su observación: un tope silencioso se leería como
          cobertura completa.
        </p>
      )}
    </div>
  );
}

/** Cobertura con los huecos ENUMERADOS: un porcentaje solo no sirve para actuar. */
function CoberturaBlock({ artifact: a }: { artifact: QaArtifact }) {
  const c = a.analysis.coverage;
  const filas: {
    label: string;
    hecho: number;
    total: number;
    faltan: string[];
    nota?: string;
  }[] = [
    {
      label: "Criterios cubiertos",
      hecho: c.criteria_covered,
      total: c.criteria_total,
      faltan: c.uncovered_criterion_refs,
    },
    {
      label: "Criterios de historias must/should",
      hecho: c.blocking_criteria_covered,
      total: c.blocking_criteria_total,
      faltan: [],
      nota: "Es la cobertura que entra en el semáforo (QA-D5).",
    },
    {
      label: "Historias con al menos un caso",
      hecho: c.stories_covered,
      total: c.stories_total,
      faltan: c.uncovered_story_refs,
    },
    {
      label: "Requisitos ejercitados",
      hecho: c.requirements_covered,
      total: c.requirements_total,
      faltan: c.uncovered_requirement_refs,
      nota: "Un requisito sin ningún caso es hallazgo, no advertencia.",
    },
  ];

  return (
    <div className="space-y-2">
      {filas.map((f) => (
        <div key={f.label} className="space-y-0.5">
          <p className="text-xs">
            <b>{f.label}:</b> {f.hecho}/{f.total}
          </p>
          {f.nota && (
            <p className="text-[11px] text-muted-foreground">{f.nota}</p>
          )}
          {f.faltan.length > 0 && (
            <p className="inline-flex flex-wrap items-center gap-1 text-xs text-amber-700">
              <AlertTriangle className="h-3 w-3" /> sin cubrir:{" "}
              {f.faltan.map((ref) => (
                <RefChip key={ref} refId={ref} />
              ))}
            </p>
          )}
        </div>
      ))}

      {c.not_testable_criterion_refs.length > 0 && (
        <div className="space-y-0.5 border-t pt-2">
          <p className="text-xs">
            <b>Declarados no verificables:</b>{" "}
            {c.not_testable_criterion_refs.length}
          </p>
          <p className="text-[11px] text-muted-foreground">
            {COVERAGE_STATUS.not_testable.hint}
          </p>
          <div className="flex flex-wrap items-center gap-1">
            {c.not_testable_criterion_refs.map((ref) => (
              <RefChip key={ref} refId={ref} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
