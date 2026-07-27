"use client";

// CENTRO DE COMANDO del artefacto EF.
//
// La página del job NO es un documento con acordeones apilados: es un hub.
// Cabecera con identidad, semáforo, mini-stats y acciones; debajo, un grid de
// tarjetas-sección que ES el índice. Todo el contenido se explora en el panel
// lateral universal (`ArtifactPanel`), donde el patrón de dos niveles sigue
// vigente: filas compactas → detalle expandible por fila.
//
// El PDF es otra cosa a propósito: `ArtifactPrintDoc` reutiliza el MISMO `render`
// de cada sección para componer el informe lineal completo.

import {
  AlertTriangle,
  Boxes,
  ClipboardCopy,
  Clock,
  Coins,
  DollarSign,
  Download,
  Eye,
  Kanban,
  Lightbulb,
  ListChecks,
  MessagesSquare,
  Printer,
  Target,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import {
  AudienceBadge,
  ConfidenceBadge,
  JobStatusBadge,
  Mono,
  OriginBadge,
} from "@/components/ef/badges";
import { ArtifactNavProvider } from "@/components/artifact/artifact-nav";
import {
  ArtifactPanel,
  type HubSection,
  type PanelRenderCtx,
  type PanelTab,
} from "@/components/artifact/artifact-panel";
import { ArtifactPrintDoc } from "@/components/artifact/artifact-print-doc";
import { HubCard, HubGrid, HubHint } from "@/components/artifact/hub-card";
import {
  FocusedQuestionFlow,
  type SheetQuestion,
} from "@/components/artifact/question-sheet";
import {
  DataList,
  DataRow,
  EmptyHint,
  IdTag,
  PrintCover,
  PrintFooter,
  PrintValidationState,
  RefChip,
  Stat,
  StatRow,
} from "@/components/artifact/primitives";
import { ArtifactSkeleton } from "@/components/artifact/artifact-skeleton";
import { ValidationControls } from "@/components/ef/validation-controls";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { ApiError } from "@/lib/api/client";
import { efApi } from "@/lib/api/ef";
import { makeRefResolver, type RefRoute } from "@/lib/artifact-refs";
import { filterByQuery, plural } from "@/lib/artifact-search";
import type {
  EFArtifact,
  JobDetail,
  QuestionStatus,
  ValidationSummary,
} from "@/lib/types/ef";
import { useArtifactHub } from "@/lib/use-artifact-hub";
import { useCelebrateOnTrue } from "@/lib/use-celebrate-on-true";
import { usePrintExpand } from "@/lib/use-print-expand";
import { useAuth } from "@/lib/auth/auth-context";
import { cn } from "@/lib/utils";

// --- secciones y rutas de referencia -----------------------------------------

/**
 * Ids de las secciones del hub. Constante de módulo (y no derivada del
 * artefacto) porque el hook del panel las necesita antes de que cargue la API, y
 * porque son las claves del deep-link (`#requisitos`).
 */
const SECTION_IDS = [
  "interpretacion",
  "preguntas",
  "requisitos",
  "modelo",
  "analisis",
] as const;

/**
 * Prefijo de id → sección (y sub-pestaña) que lo contiene. Es lo que convierte
 * cada chip REQ-F-001 / BR-003 / FLD-005 en un salto navegable entre paneles.
 */
const REF_ROUTES: RefRoute[] = [
  { prefix: "REQ-B-", sectionId: "requisitos", tabId: "negocio" },
  { prefix: "REQ-F-", sectionId: "requisitos", tabId: "funcionales" },
  { prefix: "REQ-N-", sectionId: "requisitos", tabId: "no-funcionales" },
  { prefix: "ACT-", sectionId: "modelo", tabId: "actores" },
  { prefix: "MOD-", sectionId: "modelo", tabId: "modulos" },
  { prefix: "MEN-", sectionId: "modelo", tabId: "menus" },
  { prefix: "PRO-", sectionId: "modelo", tabId: "procesos" },
  { prefix: "BR-", sectionId: "modelo", tabId: "reglas" },
  { prefix: "VAL-", sectionId: "modelo", tabId: "validaciones" },
  { prefix: "FLD-", sectionId: "modelo", tabId: "campos" },
  { prefix: "ENT-", sectionId: "modelo", tabId: "entidades" },
  { prefix: "REL-", sectionId: "modelo", tabId: "relaciones" },
  { prefix: "CRUD-", sectionId: "modelo", tabId: "crud" },
  { prefix: "API-", sectionId: "modelo", tabId: "apis" },
  { prefix: "SUP-", sectionId: "interpretacion" },
  { prefix: "Q-", sectionId: "preguntas" },
  { prefix: "AMB-", sectionId: "analisis", tabId: "ambiguedades" },
  { prefix: "MISS-", sectionId: "analisis", tabId: "faltantes" },
  { prefix: "INC-", sectionId: "analisis", tabId: "inconsistencias" },
  { prefix: "OBS-", sectionId: "analisis", tabId: "observaciones" },
];

/** Campos por los que se busca un requisito (texto, evidencia e id). */
const REQ_TEXT = (r: {
  id: string;
  text: string;
  evidence?: string | null;
  source_ref?: string | null;
}) => [r.id, r.text, r.evidence, r.source_ref];

// --- utilidades --------------------------------------------------------------

function downloadJson(artifact: EFArtifact, jobId: string) {
  const blob = new Blob([JSON.stringify(artifact, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `ef-artifact-${jobId}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

function buildProcesosText(
  artifact: EFArtifact,
  statusOf: (id: string) => QuestionStatus,
): string {
  const si = artifact.systems_interpretation;
  const lines: string[] = [];
  lines.push("INTERPRETACIÓN PARA PROCESOS");
  lines.push("");
  lines.push(si.what_process_requests);
  lines.push("");
  if (si.scope_for_systems && si.scope_for_systems.length > 0) {
    lines.push("Alcance entendido:");
    for (const s of si.scope_for_systems) lines.push(`- ${s.description}`);
    lines.push("");
  }
  if (si.apparent_out_of_scope && si.apparent_out_of_scope.length > 0) {
    lines.push("Aparentemente fuera de alcance:");
    for (const s of si.apparent_out_of_scope)
      lines.push(`- ${s.description}${s.reason ? ` (${s.reason})` : ""}`);
    lines.push("");
  }
  const pendientes = artifact.questions_for_analyst.filter(
    (q) => q.audience === "negocio" && statusOf(q.id) === "pendiente",
  );
  if (pendientes.length > 0) {
    lines.push("PREGUNTAS PENDIENTES (para Procesos):");
    pendientes.forEach((q, i) => lines.push(`${i + 1}. ${q.question}`));
  }
  return lines.join("\n");
}

// --- componente principal ----------------------------------------------------

export function ResultView({ job }: { job: JobDetail }) {
  const router = useRouter();
  const [artifact, setArtifact] = useState<EFArtifact | null>(null);
  const [summary, setSummary] = useState<ValidationSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [onlyBlocking, setOnlyBlocking] = useState(false);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [refining, setRefining] = useState(false);
  /**
   * Modo de la sección Preguntas. `null` = automático: si queda alguna
   * pendiente arranca en "una a una" (responder es la tarea), y si están todas
   * resueltas en "lista" (repasar).
   */
  const [questionMode, setQuestionMode] = useState<"lista" | "enfocado" | null>(
    null,
  );

  const hub = useArtifactHub(SECTION_IDS);
  const { printMode, printNow } = usePrintExpand();
  // Modo lectura: con acceso de solo lectura al módulo «ef» se muestra
  // todo el contenido pero se retiran las acciones de escritura (responder,
  // confirmar/corregir, regenerar). El backend las rechazaría con 403.
  const { can } = useAuth();
  const puedeEditar = can("ef", "full");
  const celebrate = useCelebrateOnTrue(
    summary?.ready_for_next_stage ?? false,
    summary != null,
  );

  const loadAll = useCallback(() => {
    Promise.all([
      efApi.getArtifact(job.job_id),
      efApi.getValidationSummary(job.job_id),
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
            : "No se pudo cargar el artefacto.",
        ),
      )
      .finally(() => setLoading(false));
  }, [job.job_id]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const reloadSummary = useCallback(async (): Promise<ValidationSummary | null> => {
    try {
      const s = await efApi.getValidationSummary(job.job_id);
      setSummary(s);
      return s;
    } catch {
      return null;
    }
  }, [job.job_id]);

  const statusOf = useCallback(
    (id: string): QuestionStatus => {
      const v = summary?.validations.find((x) => x.target_id === id);
      return v?.status ?? "pendiente";
    },
    [summary],
  );

  const respuestaOf = useCallback(
    (id: string): string | null | undefined =>
      summary?.validations.find((x) => x.target_id === id)?.respuesta,
    [summary],
  );

  // Navegación entre paneles por chip de referencia.
  const resolveRef = useMemo(() => makeRefResolver(REF_ROUTES), []);
  const canNavigateToRef = useCallback(
    (refId: string) => resolveRef(refId) !== null,
    [resolveRef],
  );
  const navigateToRef = useCallback(
    (refId: string) => {
      const target = resolveRef(refId);
      if (!target) {
        toast.info(`La referencia ${refId} no forma parte de este análisis.`);
        return;
      }
      // El modo enfocado muestra una pregunta a la vez: para resaltar una
      // concreta hay que estar en la lista.
      if (target.sectionId === "preguntas") setQuestionMode("lista");
      hub.pushEntry({ ...target, refId });
    },
    [resolveRef, hub],
  );

  const openQuestions = useCallback(() => {
    setQuestionMode(null);
    hub.openSection("preguntas");
  }, [hub]);

  function toggle(id: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const progress = useMemo(() => {
    if (!artifact) return { answered: 0, total: 0 };
    const total =
      artifact.questions_for_analyst.length +
      (artifact.systems_interpretation.interpretation_assumptions?.length ?? 0);
    const answered =
      summary?.validations.filter((v) => v.status !== "pendiente").length ?? 0;
    return { answered, total };
  }, [artifact, summary]);

  async function doRefine() {
    setRefining(true);
    try {
      const child = await efApi.refine(job.job_id);
      toast.success("Regeneración iniciada (job hijo)");
      router.push(`/agents/ef/jobs/${child.job_id}`);
    } catch (err) {
      toast.error("No se pudo regenerar", {
        description: err instanceof ApiError ? err.message : undefined,
      });
    } finally {
      setRefining(false);
    }
  }

  if (loading) {
    return <ArtifactSkeleton />;
  }
  if (error || !artifact) {
    return (
      <div className="p-6 text-sm text-red-600">
        {error ?? "Artefacto no disponible."}
      </div>
    );
  }

  const a = artifact;
  const si = a.systems_interpretation;
  const assumptions = si.interpretation_assumptions ?? [];
  const analysis = a.analysis ?? {};
  const canRefine = progress.answered >= 1;
  const ready = summary?.ready_for_next_stage ?? false;

  const reqTotal =
    a.requirements.business.length +
    a.requirements.functional.length +
    a.requirements.non_functional.length;
  const analysisTotal =
    (analysis.ambiguities?.length ?? 0) +
    (analysis.missing_info?.length ?? 0) +
    (analysis.inconsistencies?.length ?? 0) +
    (analysis.observations?.length ?? 0);
  const modelTotal =
    a.actors.length +
    a.modules.length +
    a.menus.length +
    a.processes.length +
    a.business_rules.length +
    a.validations.length +
    a.fields.length +
    a.entities.length +
    a.relationships.length +
    a.crud.length +
    a.apis.length;
  const blockingTotal = a.questions_for_analyst.filter((q) => q.blocking).length;
  const blockingRemaining = a.questions_for_analyst.filter(
    (q) => q.blocking && statusOf(q.id) === "pendiente",
  ).length;
  const blockingDone = blockingTotal > 0 && blockingRemaining === 0;
  const pendingQuestions = a.questions_for_analyst.filter(
    (q) => statusOf(q.id) === "pendiente",
  ).length;
  const assumptionsPending = assumptions.filter(
    (s) => statusOf(s.id) === "pendiente",
  ).length;
  const mode = questionMode ?? (pendingQuestions > 0 ? "enfocado" : "lista");

  // --- secciones -------------------------------------------------------------

  const sheetQuestions = a.questions_for_analyst.map(
    (q): SheetQuestion => ({
      id: q.id,
      question: q.question,
      reason: q.reason,
      blocking: q.blocking,
      audience: q.audience,
      linked_to_ref: q.linked_to_ref,
    }),
  );

  const questionControls = (id: string, onAnswered?: () => void) => (
    <ValidationControls
      readOnly={!puedeEditar}
      jobId={job.job_id}
      targetType="question"
      targetId={id}
      status={statusOf(id)}
      respuesta={respuestaOf(id)}
      onChanged={() => {
        void reloadSummary();
        onAnswered?.();
      }}
    />
  );

  const sections: HubSection[] = [
    {
      id: "interpretacion",
      title: "Interpretación",
      printTitle: "Interpretación para Sistemas",
      icon: <Lightbulb />,
      metrics: `${plural(si.scope_for_systems?.length ?? 0, "ítem")} de alcance · ${si.apparent_out_of_scope?.length ?? 0} fuera`,
      urgent: assumptionsPending > 0,
      urgentLabel: assumptionsPending > 0 ? String(assumptionsPending) : undefined,
      insight:
        assumptions.length === 0 ? (
          <span>Sin supuestos que validar</span>
        ) : assumptionsPending > 0 ? (
          <span>
            {plural(assumptionsPending, "supuesto")} por validar
          </span>
        ) : (
          <span>{plural(assumptions.length, "supuesto")} validados</span>
        ),
      render: ({ query }) => (
        <div className="space-y-5">
          <Block label="Qué pide Procesos">
            <p className="prose-measure text-sm leading-relaxed">
              {si.what_process_requests}
            </p>
          </Block>

          <Block
            label="Alcance para Sistemas"
            count={si.scope_for_systems?.length ?? 0}
          >
            <ListOrEmpty
              items={filterByQuery(query, si.scope_for_systems ?? [], (s) => [
                s.description,
                ...(s.requirement_refs ?? []),
              ])}
              empty="Sin alcance definido."
              row={(s, i) => (
                <DataRow
                  key={s.id ?? i}
                  index={i + 1}
                  right={s.requirement_refs?.map((r) => (
                    <RefChip key={r} refId={r} />
                  ))}
                >
                  {s.description}
                </DataRow>
              )}
            />
          </Block>

          <Block
            label="Aparentemente fuera de alcance"
            count={si.apparent_out_of_scope?.length ?? 0}
          >
            <ListOrEmpty
              items={filterByQuery(query, si.apparent_out_of_scope ?? [], (s) => [
                s.description,
                s.reason,
              ])}
              empty="Nada marcado fuera de alcance."
              warnOnEmpty={false}
              row={(s, i) => (
                <DataRow key={s.id ?? i} index={i + 1}>
                  {s.description}
                  {s.reason ? (
                    <span className="text-muted-foreground"> — {s.reason}</span>
                  ) : null}
                </DataRow>
              )}
            />
          </Block>

          <Block label="Supuestos de interpretación" count={assumptions.length}>
            {(() => {
              const items = filterByQuery(query, assumptions, (s) => [
                s.id,
                s.assumption,
                s.rationale,
              ]);
              if (items.length === 0)
                return <EmptyHint>Sin supuestos que mostrar.</EmptyHint>;
              return (
                <div className="space-y-2">
                  {items.map((s) => (
                    <div
                      key={s.id}
                      id={`ref-${s.id}`}
                      className="print-atom rounded-lg border p-3"
                    >
                      <div className="flex flex-wrap items-center gap-2">
                        <IdTag id={s.id} />
                        <OriginBadge origin={s.origin} />
                        <ConfidenceBadge value={s.confidence} />
                      </div>
                      <p className="mt-1.5 text-sm">{s.assumption}</p>
                      {s.rationale && (
                        <p className="text-xs text-muted-foreground">
                          {s.rationale}
                        </p>
                      )}
                      <div className="print:hidden">
                        <ValidationControls
                          readOnly={!puedeEditar}
                          jobId={job.job_id}
                          targetType="assumption"
                          targetId={s.id}
                          status={statusOf(s.id)}
                          respuesta={respuestaOf(s.id)}
                          onChanged={reloadSummary}
                        />
                      </div>
                      <PrintValidationState
                        status={statusOf(s.id)}
                        respuesta={respuestaOf(s.id)}
                      />
                    </div>
                  ))}
                </div>
              );
            })()}
          </Block>
        </div>
      ),
    },

    {
      id: "preguntas",
      title: "Preguntas",
      printTitle: "Preguntas al analista",
      icon: <MessagesSquare />,
      count: a.questions_for_analyst.length,
      metrics: `${a.questions_for_analyst.length} · ${plural(blockingTotal, "bloqueante")}`,
      urgent: blockingRemaining > 0,
      urgentLabel: blockingRemaining > 0 ? String(blockingRemaining) : undefined,
      insight:
        blockingRemaining > 0 ? (
          <span>{plural(blockingRemaining, "bloqueante")} sin responder</span>
        ) : (
          <span>
            {blockingTotal > 0
              ? "Bloqueantes resueltas"
              : "Sin preguntas bloqueantes"}{" "}
            · {progress.answered} de {progress.total} respondidas
          </span>
        ),
      searchable: mode === "lista",
      actions: (
        <div className="flex flex-wrap items-center gap-2">
          <Segmented
            value={mode}
            onChange={setQuestionMode}
            options={[
              { value: "enfocado", label: "Una a una" },
              { value: "lista", label: "Lista" },
            ]}
          />
          {mode === "lista" && (
            <Segmented
              value={onlyBlocking ? "bloq" : "todas"}
              onChange={(v) => setOnlyBlocking(v === "bloq")}
              options={[
                { value: "todas", label: "Todas" },
                { value: "bloq", label: "Bloqueantes" },
              ]}
            />
          )}
        </div>
      ),
      render: ({ query, forPrint }) => {
        // En el PDF siempre la lista completa: un informe no se lee de una en una.
        if (!forPrint && mode === "enfocado") {
          return (
            <FocusedQuestionFlow
              questions={sheetQuestions}
              statusOf={statusOf}
              renderControls={(q, onAnswered) =>
                questionControls(q.id, onAnswered)
              }
            />
          );
        }
        const base = forPrint
          ? a.questions_for_analyst
          : onlyBlocking
            ? a.questions_for_analyst.filter((q) => q.blocking)
            : a.questions_for_analyst;
        const items = filterByQuery(query, base, (q) => [
          q.id,
          q.question,
          q.reason,
          q.linked_to_ref,
        ]);
        if (items.length === 0) {
          return (
            <EmptyHint warn={!onlyBlocking && !query}>
              {query
                ? "Ninguna pregunta coincide con la búsqueda."
                : onlyBlocking
                  ? "Sin preguntas bloqueantes."
                  : "Sin preguntas."}
            </EmptyHint>
          );
        }
        return (
          <div className="space-y-2">
            {items.map((q) => (
              <div
                key={q.id}
                id={`ref-${q.id}`}
                className={cn(
                  "print-atom rounded-lg border p-3",
                  q.blocking && "border-red-300 bg-red-50/40",
                )}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <IdTag id={q.id} />
                  <AudienceBadge audience={q.audience} />
                  {q.blocking && <Badge className="bg-red-600">bloqueante</Badge>}
                  {q.linked_to_ref && (
                    <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                      ligada a <RefChip refId={q.linked_to_ref} />
                    </span>
                  )}
                </div>
                <p className="mt-1.5 text-sm font-medium">{q.question}</p>
                <p className="text-xs text-muted-foreground">Motivo: {q.reason}</p>
                <div className="print:hidden">{questionControls(q.id)}</div>
                <PrintValidationState
                  status={statusOf(q.id)}
                  respuesta={respuestaOf(q.id)}
                />
              </div>
            ))}
          </div>
        );
      },
    },

    {
      id: "requisitos",
      title: "Requisitos",
      icon: <ListChecks />,
      count: reqTotal,
      metrics: `${reqTotal} · ${a.requirements.functional.length} funcionales`,
      insight: (
        <span>
          {a.requirements.business.length} de negocio ·{" "}
          {a.requirements.non_functional.length} no funcionales ·{" "}
          {plural(
            a.requirements.functional.filter((r) => r.origin === "derived").length,
            "derivado",
          )}
        </span>
      ),
      tabs: (
        [
          ["negocio", "Negocio", a.requirements.business],
          ["funcionales", "Funcionales", a.requirements.functional],
          ["no-funcionales", "No funcionales", a.requirements.non_functional],
        ] as const
      ).map(
        ([id, label, list]): PanelTab => ({
          id,
          label,
          count: list.length,
          matchCount: (q) => filterByQuery(q, list, REQ_TEXT).length,
          render: (ctx) => (
            <RequirementList
              list={list}
              ctx={ctx}
              expanded={expanded}
              onToggle={toggle}
            />
          ),
        }),
      ),
    },

    {
      id: "modelo",
      title: "Modelo",
      icon: <Boxes />,
      count: modelTotal,
      metrics: `${plural(modelTotal, "ítem")} · ${plural(a.entities.length, "entidad", "entidades")}`,
      insight: (
        <span>
          {plural(a.processes.length, "proceso")} ·{" "}
          {plural(a.business_rules.length, "regla")} ·{" "}
          {plural(a.apis.length, "API")}
        </span>
      ),
      tabs: [
        itemTab("actores", "Actores", a.actors, (x) => [x.id, x.name, x.description], (x) => x.name),
        itemTab("modulos", "Módulos", a.modules, (x) => [x.id, x.name, x.description], (x) => x.name),
        itemTab(
          "menus",
          "Menús",
          a.menus,
          (x) => [x.id, x.name, x.path],
          (x) => (
            <>
              {x.name} {x.path ? <Mono>{x.path}</Mono> : null}
            </>
          ),
        ),
        itemTab(
          "procesos",
          "Procesos",
          a.processes,
          (x) => [x.id, x.name, x.description, ...(x.steps ?? [])],
          (x) => (
            <>
              {x.name}
              {x.steps && x.steps.length > 0 ? (
                <span className="text-xs text-muted-foreground">
                  {" "}
                  · {x.steps.join(" → ")}
                </span>
              ) : null}
            </>
          ),
        ),
        itemTab(
          "reglas",
          "Reglas",
          a.business_rules,
          (x) => [x.id, x.statement],
          (x) => x.statement,
        ),
        itemTab(
          "validaciones",
          "Validaciones",
          a.validations,
          (x) => [x.id, x.rule, x.field_ref],
          (x) => (
            <>
              {x.rule}{" "}
              {x.field_ref ? (
                <span className="text-xs">
                  (<RefChip refId={x.field_ref} />)
                </span>
              ) : null}
            </>
          ),
        ),
        itemTab(
          "campos",
          "Campos",
          a.fields,
          (x) => [x.id, x.name, x.data_type, x.entity_ref],
          (x) => (
            <>
              <Mono>{x.name}</Mono>
              <span className="text-xs text-muted-foreground">
                {" "}
                {x.data_type ?? "?"} {x.required ? "· requerido" : ""}
                {x.entity_ref ? " · " : ""}
              </span>
              {x.entity_ref ? <RefChip refId={x.entity_ref} /> : null}
            </>
          ),
        ),
        itemTab(
          "entidades",
          "Entidades",
          a.entities,
          (x) => [x.id, x.name, x.description],
          (x) => x.name,
        ),
        itemTab(
          "relaciones",
          "Relaciones",
          a.relationships,
          (x) => [x.id, x.source_entity_ref, x.target_entity_ref, x.cardinality],
          (x) => (
            <>
              <RefChip refId={x.source_entity_ref} /> <Mono>{x.cardinality}</Mono>{" "}
              <RefChip refId={x.target_entity_ref} />
            </>
          ),
        ),
        itemTab(
          "crud",
          "CRUD",
          a.crud,
          (x) => [x.id, x.entity_ref],
          (x) => (
            <>
              <RefChip refId={x.entity_ref} />
              <span className="ml-2 font-mono text-xs">
                {x.create ? "C" : "-"}
                {x.read ? "R" : "-"}
                {x.update ? "U" : "-"}
                {x.delete ? "D" : "-"}
              </span>
            </>
          ),
        ),
        itemTab(
          "apis",
          "APIs",
          a.apis,
          (x) => [x.id, x.method, x.path, x.description],
          (x) => (
            <Mono>
              {x.method} {x.path}
            </Mono>
          ),
        ),
      ],
    },

    {
      id: "analisis",
      title: "Análisis crítico",
      icon: <AlertTriangle />,
      count: analysisTotal,
      metrics: plural(analysisTotal, "hallazgo"),
      insight: (
        <span>
          {plural(analysis.ambiguities?.length ?? 0, "ambigüedad", "ambigüedades")}{" "}
          · {plural(analysis.missing_info?.length ?? 0, "faltante")} ·{" "}
          {plural(
            analysis.inconsistencies?.length ?? 0,
            "inconsistencia",
          )}
        </span>
      ),
      tabs: [
        itemTab(
          "ambiguedades",
          "Ambigüedades",
          analysis.ambiguities ?? [],
          (x) => [x.id, x.description],
          (x) => x.description,
        ),
        itemTab(
          "faltantes",
          "Faltantes",
          analysis.missing_info ?? [],
          (x) => [x.id, x.description, x.expected_where],
          (x) => (
            <>
              {x.description}
              {x.expected_where ? (
                <span className="text-xs text-muted-foreground">
                  {" "}
                  — esperado en: {x.expected_where}
                </span>
              ) : null}
            </>
          ),
        ),
        itemTab(
          "inconsistencias",
          "Inconsistencias",
          analysis.inconsistencies ?? [],
          (x) => [x.id, x.description, ...(x.conflicting_refs ?? [])],
          (x) => (
            <>
              {x.description}
              {x.conflicting_refs && x.conflicting_refs.length > 0 ? (
                <span className="ml-1 inline-flex flex-wrap gap-1">
                  {x.conflicting_refs.map((r) => (
                    <RefChip key={r} refId={r} />
                  ))}
                </span>
              ) : null}
            </>
          ),
        ),
        itemTab(
          "observaciones",
          "Observaciones",
          analysis.observations ?? [],
          (x) => [x.id, x.description, x.reason],
          (x) => (
            <>
              {x.description}
              {x.reason ? (
                <span className="text-xs text-muted-foreground"> — {x.reason}</span>
              ) : null}
            </>
          ),
        ),
      ],
    },
  ];

  return (
    <ArtifactNavProvider
      navigateToRef={navigateToRef}
      canNavigateToRef={canNavigateToRef}
    >
      <div className="flex h-full flex-col">
        <PrintCover
          kind="Análisis de Especificación Funcional"
          title={a.source.filename || "Análisis EF"}
          subtitle={a.summary}
          version="1.2.0"
          stats={[
            { label: "requisitos", value: String(reqTotal) },
            { label: "preguntas", value: String(a.questions_for_analyst.length) },
            {
              label: "cobertura",
              value: `${Math.round(a.metrics.coverage * 100)}%`,
            },
            { label: "costo", value: `$${a.metrics.cost.toFixed(4)}` },
          ]}
        />
        <PrintFooter title="Análisis de Especificación Funcional" />

        {/* Barra superior de afinamiento */}
        <div className="sticky top-0 z-10 border-b bg-background/95 px-6 py-3 backdrop-blur print:hidden">
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <span className="font-heading font-semibold">EF v1.2.0</span>
            <Badge variant="outline">
              {job.parent_job_id ? "v2 · afinamiento" : "v1 · original"}
            </Badge>
            {job.parent_job_id && (
              <Link
                href={`/agents/ef/jobs/${job.parent_job_id}`}
                className="text-xs text-muted-foreground underline-offset-2 hover:text-primary hover:underline"
              >
                ver original (<Mono>{job.parent_job_id}</Mono>)
              </Link>
            )}
            <span className="text-xs text-muted-foreground">
              {progress.answered} de {progress.total} respondidas
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
              {ready ? "Listo para el Agente Scrum" : "Pendiente de afinamiento"}
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

            <div className="ml-auto flex flex-wrap gap-2">
              {puedeEditar && a.questions_for_analyst.length > 0 && (
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
              )}
              <Button
                variant="ghost"
                size="sm"
                className="gap-1.5"
                onClick={() =>
                  void navigator.clipboard
                    .writeText(buildProcesosText(a, statusOf))
                    .then(() => toast.success("Copiado para Procesos"))
                }
              >
                <ClipboardCopy className="h-3.5 w-3.5" />
                Copiar
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="gap-1.5"
                onClick={printNow}
              >
                <Printer className="h-3.5 w-3.5" />
                Exportar PDF
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="gap-1.5"
                onClick={() => downloadJson(a, job.job_id)}
              >
                <Download className="h-3.5 w-3.5" />
                JSON
              </Button>
              {puedeEditar && (
                <Dialog>
                  <DialogTrigger
                    render={
                      <Button size="sm" disabled={!canRefine}>
                        Regenerar EF afinada
                      </Button>
                    }
                  />
                  <DialogContent>
                    <DialogHeader>
                      <DialogTitle>Regenerar EF afinada</DialogTitle>
                      <DialogDescription>
                        Se creará un análisis hijo reinyectando tus respuestas y se
                        ejecutará el modelo real.
                      </DialogDescription>
                    </DialogHeader>
                    <div className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800">
                      Costo estimado: ~$
                      {a.metrics.cost.toFixed(4)} (similar al análisis anterior).
                      Esta acción consume tokens de la API.
                    </div>
                    <DialogFooter>
                      <Button onClick={doRefine} disabled={refining || !canRefine}>
                        {refining ? "Regenerando…" : "Confirmar y regenerar"}
                      </Button>
                    </DialogFooter>
                  </DialogContent>
                </Dialog>
              )}
            </div>
          </div>
        </div>

        {/* Cabecera: estado, fuente y mini-stats */}
        <div className="border-b px-6 py-3 print:hidden">
          <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
            <StatRow>
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
              <Stat
                icon={<Clock />}
                value={`${a.metrics.duration}s`}
                label="duración"
              />
              <Stat
                icon={<Target />}
                value={`${Math.round(a.metrics.coverage * 100)}%`}
                label="cobertura"
              />
            </StatRow>
            <div className="ml-auto flex items-center gap-3 text-xs text-muted-foreground">
              <JobStatusBadge status={job.status} />
              <span>
                {a.source.type} · {a.source.fidelity}
                {a.source.filename ? ` · ${a.source.filename}` : ""}
              </span>
            </div>
          </div>
          <p className="prose-measure mt-2 line-clamp-2 text-sm text-muted-foreground">
            {a.summary}
          </p>
        </div>

        {/* EL HUB: el grid de tarjetas ES el índice del artefacto. */}
        <div className="px-4 py-5 md:px-6 print:hidden">
          {blockingDone && (
            <div
              className={cn(
                "mb-4 rounded-xl border p-4",
                // En verde, el rim-light esmeralda sustituye al borde plano (de
                // ahí `border-transparent`: si no, doble anillo).
                ready
                  ? "gradient-border gradient-border-emerald border-transparent bg-emerald-50"
                  : "border-amber-300 bg-amber-50",
              )}
            >
              <div className="flex flex-wrap items-center gap-3">
                <span
                  className={cn(
                    "flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-white",
                    ready ? "bg-emerald-500" : "bg-amber-500",
                  )}
                >
                  ✓
                </span>
                <div className="min-w-0 flex-1">
                  <div className="font-heading text-sm font-semibold">
                    {ready
                      ? "EF lista para planificar"
                      : "Sin preguntas bloqueantes pendientes"}
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {ready
                      ? "El semáforo está en verde. Genera el plan Scrum a partir de esta EF."
                      : "Faltan otras condiciones del semáforo (cobertura o requisitos)."}
                  </p>
                </div>
                {ready && (
                  <Link
                    href="/agents/scrum/new"
                    className={buttonVariants({ size: "sm", className: "gap-1.5" })}
                  >
                    <Kanban className="h-3.5 w-3.5" />
                    Generar plan Scrum
                  </Link>
                )}
              </div>
            </div>
          )}

          <HubGrid>
            {sections.map((s) => (
              <HubCard
                key={s.id}
                module="ef"
                icon={s.icon}
                title={s.title}
                metrics={s.metrics}
                insight={s.insight}
                urgent={s.urgent}
                urgentLabel={s.urgentLabel}
                onOpen={() =>
                  s.id === "preguntas" ? openQuestions() : hub.openSection(s.id)
                }
              />
            ))}
          </HubGrid>
          <HubHint />
        </div>

        <ArtifactPanel hub={hub} sections={sections} module="ef" />
        <ArtifactPrintDoc sections={sections} active={printMode} />
      </div>
    </ArtifactNavProvider>
  );
}

// --- subcomponentes ----------------------------------------------------------

/** Sub-bloque con etiqueta dentro del cuerpo del panel. */
function Block({
  label,
  count,
  children,
}: {
  label: string;
  count?: number;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="mb-1.5 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wide text-meta-foreground">
        {label}
        {count !== undefined && (
          <span
            className={cn(
              "tabular-nums",
              count === 0 ? "text-amber-600" : "text-foreground/70",
            )}
          >
            {count}
          </span>
        )}
      </div>
      {children}
    </div>
  );
}

/** Lista hairline o estado vacío explícito. */
function ListOrEmpty<T>({
  items,
  row,
  empty,
  warnOnEmpty = true,
}: {
  items: T[];
  row: (item: T, index: number) => React.ReactNode;
  empty: string;
  warnOnEmpty?: boolean;
}) {
  if (items.length === 0) return <EmptyHint warn={warnOnEmpty}>{empty}</EmptyHint>;
  return <DataList>{items.map((item, i) => row(item, i))}</DataList>;
}

/**
 * Fábrica de sub-pestañas de lista: conteo total, conteo de coincidencias para
 * el buscador y filas con id. Evita repetir once veces la misma estructura en el
 * Modelo del EF.
 */
function itemTab<T extends { id: string; origin?: "stated" | "derived" | null }>(
  id: string,
  label: string,
  items: readonly T[],
  text: (item: T) => (string | number | null | undefined)[],
  row: (item: T) => React.ReactNode,
): PanelTab {
  return {
    id,
    label,
    count: items.length,
    matchCount: (q) => filterByQuery(q, items, text).length,
    render: (ctx) => <ItemList items={items} ctx={ctx} text={text} row={row} />,
  };
}

/** Filas del modelo y del análisis: id + badge de origen a la derecha. */
function ItemList<
  T extends { id: string; origin?: "stated" | "derived" | null },
>({
  items,
  ctx,
  text,
  row,
}: {
  items: readonly T[];
  ctx: PanelRenderCtx;
  text: (item: T) => (string | number | null | undefined)[];
  row: (item: T) => React.ReactNode;
}) {
  const shown = filterByQuery(ctx.query, items, text);
  if (shown.length === 0) {
    return (
      <EmptyHint warn={!ctx.query}>
        {ctx.query ? "Nada coincide con la búsqueda." : "Vacío."}
      </EmptyHint>
    );
  }
  return (
    <DataList>
      {shown.map((x) => (
        <DataRow
          key={x.id}
          id={x.id}
          right={
            <>
              {x.origin === "derived" ? <OriginBadge origin={x.origin} /> : null}
              <IdTag id={x.id} />
            </>
          }
        >
          {row(x)}
        </DataRow>
      ))}
    </DataList>
  );
}

/**
 * Requisitos: fila compacta con el detalle (source_ref + evidencia verbatim)
 * plegado. En impresión el detalle se muestra siempre — el informe no se pliega.
 */
function RequirementList({
  list,
  ctx,
  expanded,
  onToggle,
}: {
  list: EFArtifact["requirements"]["business"];
  ctx: PanelRenderCtx;
  expanded: Set<string>;
  onToggle: (id: string) => void;
}) {
  const shown = filterByQuery(ctx.query, list, (r) => [
    r.id,
    r.text,
    r.evidence,
    r.source_ref,
  ]);
  if (shown.length === 0) {
    return (
      <EmptyHint warn={!ctx.query}>
        {ctx.query ? "Nada coincide con la búsqueda." : "Sin requisitos."}
      </EmptyHint>
    );
  }
  return (
    <DataList>
      {shown.map((r, i) => {
        const open = ctx.forPrint || expanded.has(r.id);
        return (
          <div key={r.id} id={`ref-${r.id}`} className="print-atom">
            <button
              type="button"
              onClick={() => onToggle(r.id)}
              aria-expanded={open}
              className="flex w-full items-start gap-3 px-3 py-2 text-left transition-colors hover:bg-primary/[0.04]"
            >
              <span className="w-5 shrink-0 pt-0.5 text-right font-mono text-[11px] tabular-nums text-meta-foreground">
                {i + 1}
              </span>
              <span className="min-w-0 flex-1 text-sm">{r.text}</span>
              <span className="flex shrink-0 items-center gap-1.5 pt-0.5">
                <OriginBadge origin={r.origin} />
                <ConfidenceBadge value={r.confidence} />
                <IdTag id={r.id} />
              </span>
            </button>
            {open && (
              <div className="space-y-1 px-3 pb-3 pl-11 text-xs">
                <div>
                  source_ref: <Mono>{r.source_ref ?? "—"}</Mono>
                </div>
                <div className="text-muted-foreground">evidence:</div>
                <pre className="whitespace-pre-wrap rounded bg-muted p-2 font-mono text-[11px]">
                  {r.evidence ?? "— sin evidencia —"}
                </pre>
              </div>
            )}
          </div>
        );
      })}
    </DataList>
  );
}

/** Conmutador segmentado compacto (modo de preguntas, filtros del panel). */
function Segmented<T extends string>({
  value,
  onChange,
  options,
}: {
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: string }[];
}) {
  return (
    <div className="flex rounded-lg border bg-muted/40 p-0.5 text-xs">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          onClick={() => onChange(o.value)}
          aria-pressed={value === o.value}
          className={cn(
            "rounded-md px-2 py-1 transition-colors duration-150",
            value === o.value
              ? "bg-background font-medium text-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
