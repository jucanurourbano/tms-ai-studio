"use client";

// CENTRO DE COMANDO del plan Scrum. Mismo patrón que el EF (ver
// `components/ef/result-view.tsx`): cabecera + grid de tarjetas-sección, todo el
// contenido en el panel lateral universal y el PDF como documento lineal.
//
// Lo propio del Scrum es la capa de ASIGNACIÓN al equipo: vive fuera del
// artefacto y se superpone al plan (selector por historia y por sprint, carga por
// sprint, filtro por responsable). Se mantiene íntegra dentro del panel.

import {
  AlertTriangle,
  ChevronRight,
  Coins,
  DollarSign,
  Download,
  Eye,
  FileDown,
  Hash,
  Layers,
  ListChecks,
  ListOrdered,
  MessagesSquare,
  Printer,
  Send,
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
} from "@/components/ef/badges";
import { ArtifactNavProvider } from "@/components/artifact/artifact-nav";
import {
  ArtifactPanel,
  type HubSection,
  type PanelRenderCtx,
} from "@/components/artifact/artifact-panel";
import { ArtifactPrintDoc } from "@/components/artifact/artifact-print-doc";
import {
  ActionGroup,
  HeaderActions,
  HubCard,
  HubGrid,
  HubHint,
} from "@/components/artifact/hub-card";
import {
  FocusedQuestionFlow,
  type SheetQuestion,
} from "@/components/artifact/focused-questions";
import {
  DataList,
  DataRow,
  EmptyHint,
  GroupLabel,
  IdTag,
  PrintCover,
  PrintFooter,
  PrintValidationState,
  RefChip,
  Stat,
  StatRow,
  StatusPill,
} from "@/components/artifact/primitives";
import { ArtifactSkeleton } from "@/components/artifact/artifact-skeleton";
import {
  AssigneeBadge,
  AssigneeSelect,
  SprintAssigneeSelect,
  SprintLoad,
} from "@/components/scrum/assignee";
import { ScrumValidationControls } from "@/components/scrum/validation-controls";
import { Badge } from "@/components/ui/badge";
import { DataTable, type DataColumn } from "@/components/ui/data-table";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
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
import { scrumApi } from "@/lib/api/scrum";
import { makeRefResolver, type RefRoute } from "@/lib/artifact-refs";
import { filterByQuery, plural } from "@/lib/artifact-search";
import type { QuestionStatus } from "@/lib/types/ef";
import type {
  MoscowPriority,
  ScrumArtifact,
  ScrumJobDetail,
  ScrumValidationSummary,
  SprintAssignment,
  Story,
  StoryAssignment,
  TeamMember,
} from "@/lib/types/scrum";
import {
  assigneeMap,
  computeSprintLoads,
  matchesPersonFilter,
  SIN_ASIGNAR,
  sourceMap,
  sprintAssigneeMap,
  unassignedPoints,
} from "@/lib/scrum-assignments";
import { useArtifactHub } from "@/lib/use-artifact-hub";
import { useCelebrateOnTrue } from "@/lib/use-celebrate-on-true";
import { usePrintExpand } from "@/lib/use-print-expand";
import { useAuth } from "@/lib/auth/auth-context";
import { NativeSelect } from "@/components/ui/native-select";
import { cn } from "@/lib/utils";

// --- secciones y rutas de referencia -----------------------------------------

const SECTION_IDS = [
  "backlog",
  "sprints",
  "historias",
  "epicas",
  "preguntas",
  "analisis",
] as const;

/**
 * Un plan Scrum cita ids del EF (REQ-F-…, BR-…): esos NO se resuelven aquí a
 * propósito — no viven en este artefacto y el chip lo dice en vez de fingir.
 */
const REF_ROUTES: RefRoute[] = [
  { prefix: "EPIC-", sectionId: "epicas" },
  { prefix: "US-", sectionId: "historias" },
  { prefix: "AC-", sectionId: "historias" },
  { prefix: "SPRINT-", sectionId: "sprints" },
  { prefix: "Q-", sectionId: "preguntas" },
  { prefix: "RISK-", sectionId: "analisis", tabId: "riesgos" },
  { prefix: "OBS-", sectionId: "analisis", tabId: "observaciones" },
];

// --- badges de dominio -------------------------------------------------------

const MOSCOW_STYLE: Record<MoscowPriority, string> = {
  must: "border-red-300 bg-red-50 text-red-700",
  should: "border-amber-300 bg-amber-50 text-amber-700",
  could: "border-sky-300 bg-sky-50 text-sky-700",
  wont: "border-slate-300 bg-slate-50 text-slate-500",
};

const MOSCOW_TIP: Record<MoscowPriority, string> = {
  must: "Must — imprescindible para el MVP.",
  should: "Should — importante, pero no bloqueante.",
  could: "Could — deseable si hay capacidad.",
  wont: "Won't — fuera de alcance por ahora.",
};

function MoscowBadge({ priority }: { priority?: MoscowPriority | null }) {
  if (!priority) return <span className="text-xs text-muted-foreground">—</span>;
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <Badge
            variant="outline"
            className={cn("cursor-help", MOSCOW_STYLE[priority])}
          >
            {priority}
          </Badge>
        }
      />
      <TooltipContent>{MOSCOW_TIP[priority]}</TooltipContent>
    </Tooltip>
  );
}

function PointsBadge({ points }: { points?: number | null }) {
  if (points === null || points === undefined) {
    return (
      <Badge variant="outline" className="border-amber-300 bg-amber-50 text-amber-700">
        sin estimar
      </Badge>
    );
  }
  return (
    <Badge variant="outline" className="font-mono tabular-nums">
      {points} pts
    </Badge>
  );
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

/** Campos por los que se busca una historia. */
const STORY_TEXT = (s: Story) => [
  s.id,
  s.statement,
  s.goal,
  s.epic_ref,
  s.priority,
  s.estimation_rationale,
  ...s.source_refs.requirement_refs,
  ...s.source_refs.rule_refs,
  ...s.acceptance_criteria.map((c) => c.text ?? ""),
  ...s.acceptance_criteria.flatMap((c) => [c.given, c.when, c.then]),
];

// --- componente principal ----------------------------------------------------

export function ScrumResultView({ job }: { job: ScrumJobDetail }) {
  const router = useRouter();
  const [artifact, setArtifact] = useState<ScrumArtifact | null>(null);
  const [summary, setSummary] = useState<ScrumValidationSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [onlyBlocking, setOnlyBlocking] = useState(false);
  const [refining, setRefining] = useState(false);
  const [expandedStories, setExpandedStories] = useState<Set<string>>(new Set());
  const [questionMode, setQuestionMode] = useState<"lista" | "enfocado" | null>(
    null,
  );
  // Equipo y asignaciones: viven FUERA del artefacto, así que se cargan aparte.
  const [team, setTeam] = useState<TeamMember[]>([]);
  const [assignments, setAssignments] = useState<StoryAssignment[]>([]);
  const [sprintAssignments, setSprintAssignments] = useState<SprintAssignment[]>(
    [],
  );
  const [assigningId, setAssigningId] = useState<string | null>(null);
  /** Filtro "ver historias de": id de colaborador, "" = todas. */
  const [personFilter, setPersonFilter] = useState("");

  const hub = useArtifactHub(SECTION_IDS);
  const { printMode, printNow } = usePrintExpand();
  // Modo lectura: con acceso de solo lectura al módulo «scrum» se muestra
  // todo el contenido pero se retiran las acciones de escritura (responder,
  // confirmar/corregir, regenerar). El backend las rechazaría con 403.
  const { can } = useAuth();
  const puedeEditar = can("scrum", "full");
  const celebrate = useCelebrateOnTrue(
    summary?.ready_for_next_stage ?? false,
    summary != null,
  );

  const toggleStory = (id: string) =>
    setExpandedStories((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const loadAll = useCallback(() => {
    Promise.all([
      scrumApi.getArtifact(job.job_id),
      scrumApi.getValidationSummary(job.job_id),
    ])
      .then(([a, s]) => {
        setArtifact(a);
        setSummary(s);
        setError(null);
      })
      .catch((err) =>
        setError(
          err instanceof ApiError ? err.message : "No se pudo cargar el plan.",
        ),
      )
      .finally(() => setLoading(false));
  }, [job.job_id]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  // Equipo y asignaciones. Se piden en paralelo y no bloquean el artefacto: si
  // fallan (p. ej. permisos), el plan se sigue viendo sin la capa de asignación.
  const loadAssignments = useCallback(() => {
    scrumApi
      .assignments(job.job_id)
      .then((d) => {
        setAssignments(d.items);
        setSprintAssignments(d.sprints);
      })
      .catch(() => {
        /* la vista funciona sin asignaciones */
      });
  }, [job.job_id]);

  useEffect(() => {
    loadAssignments();
    scrumApi
      .team()
      .then((d) => setTeam(d.items))
      .catch(() => {
        /* sin equipo, el selector queda vacío pero la vista no se rompe */
      });
  }, [loadAssignments]);

  const onAssignSprint = useCallback(
    async (sprintId: string, userId: string | null) => {
      setAssigningId(sprintId);
      try {
        await scrumApi.assignSprint(job.job_id, sprintId, userId);
        toast.success(
          userId
            ? "Sprint asignado · sus historias sin responsable propio lo heredan"
            : "Asignación de sprint retirada",
        );
        loadAssignments();
      } catch (err) {
        toast.error("No se pudo asignar el sprint", {
          description: err instanceof ApiError ? err.message : undefined,
        });
      } finally {
        setAssigningId(null);
      }
    },
    [job.job_id, loadAssignments],
  );

  const onAssign = useCallback(
    async (storyId: string, userId: string | null) => {
      setAssigningId(storyId);
      try {
        await scrumApi.assignStory(job.job_id, storyId, userId);
        toast.success(userId ? "Historia asignada" : "Asignación retirada");
        loadAssignments();
      } catch (err) {
        toast.error("No se pudo asignar", {
          description: err instanceof ApiError ? err.message : undefined,
        });
      } finally {
        setAssigningId(null);
      }
    },
    [job.job_id, loadAssignments],
  );

  const reloadSummary = useCallback(async (): Promise<ScrumValidationSummary | null> => {
    try {
      const s = await scrumApi.getValidationSummary(job.job_id);
      setSummary(s);
      return s;
    } catch {
      return null;
    }
  }, [job.job_id]);

  const statusOf = useCallback(
    (id: string): QuestionStatus =>
      summary?.validations.find((x) => x.target_id === id)?.status ?? "pendiente",
    [summary],
  );
  const respuestaOf = useCallback(
    (id: string): string | null | undefined =>
      summary?.validations.find((x) => x.target_id === id)?.respuesta,
    [summary],
  );

  const answered = useMemo(
    () => summary?.validations.filter((v) => v.status !== "pendiente").length ?? 0,
    [summary],
  );

  const resolveRef = useMemo(() => makeRefResolver(REF_ROUTES), []);
  const canNavigateToRef = useCallback(
    (refId: string) => resolveRef(refId) !== null,
    [resolveRef],
  );
  const navigateToRef = useCallback(
    (refId: string) => {
      const target = resolveRef(refId);
      if (!target) {
        toast.info(
          `${refId} pertenece a la EF de origen, no al plan. Ábrela para verlo.`,
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

  async function doRefine() {
    setRefining(true);
    try {
      const child = await scrumApi.refine(job.job_id);
      toast.success("Regeneración iniciada (job hijo)");
      router.push(`/agents/scrum/jobs/${child.job_id}`);
    } catch (err) {
      toast.error("No se pudo regenerar", {
        description: err instanceof ApiError ? err.message : undefined,
      });
    } finally {
      setRefining(false);
    }
  }

  async function doExport(format: "csv" | "json") {
    try {
      const res = await scrumApi.export(job.job_id, format);
      if (format === "csv") {
        download(res.content as string, res.filename, "text/csv");
      } else {
        download(
          JSON.stringify(res.content, null, 2),
          res.filename,
          "application/json",
        );
      }
      toast.success("Export generado (compatible con ClickUp)");
    } catch (err) {
      toast.error("No se pudo exportar", {
        description: err instanceof ApiError ? err.message : undefined,
      });
    }
  }

  if (loading) {
    return <ArtifactSkeleton />;
  }
  if (error || !artifact) {
    return (
      <div className="p-6 text-sm text-red-600">
        {error ?? "Plan no disponible."}
      </div>
    );
  }

  const a = artifact;
  const ready = summary?.ready_for_next_stage ?? false;
  const checks = summary?.checks;
  const storyById = new Map<string, Story>(a.stories.map((s) => [s.id, s]));

  // Capa de asignación: derivada de artefacto + asignaciones (lógica pura y
  // testeada en `lib/scrum-assignments.ts`).
  const assigneeOf = assigneeMap(assignments);
  const sourceOf = sourceMap(assignments);
  const sprintAssigneeOf = sprintAssigneeMap(sprintAssignments);
  const loadsOfSprint = (storyIds: string[]) =>
    computeSprintLoads(storyIds, storyById, assigneeOf);
  const unassignedPointsOf = (storyIds: string[]) =>
    unassignedPoints(storyIds, storyById, assigneeOf);

  const cov = a.analysis.coverage;
  const canRefine = answered >= 1;
  const blockingTotal = a.questions_for_po.filter((q) => q.blocking).length;
  const blockingRemaining = a.questions_for_po.filter(
    (q) => q.blocking && statusOf(q.id) === "pendiente",
  ).length;
  const blockingDone = blockingTotal > 0 && blockingRemaining === 0;
  const pendingQuestions = a.questions_for_po.filter(
    (q) => statusOf(q.id) === "pendiente",
  ).length;
  const mode = questionMode ?? (pendingQuestions > 0 ? "enfocado" : "lista");

  const estimated = a.stories.filter((s) => s.story_points != null).length;
  const unestimated = a.stories.length - estimated;
  const mustCount = a.stories.filter((s) => s.priority === "must").length;

  // El backlog usa el patrón de tabla de la app: tabla en escritorio, una card
  // por historia en móvil (nada de scroll horizontal).
  const backlogRows = (query: string) =>
    a.product_backlog.ordered_story_ids
      .filter((sid) => matchesPersonFilter(sid, personFilter, assigneeOf))
      .filter((sid) => {
        const s = storyById.get(sid);
        return s ? filterByQuery(query, [s], STORY_TEXT).length > 0 : !query;
      });

  const backlogColumns = (rows: string[]): DataColumn<string>[] => [
    {
      key: "orden",
      label: "#",
      width: "w-12",
      numeric: true,
      cardRole: "hidden",
      render: (sid) => (
        <span className="text-[11px] text-meta-foreground">
          {rows.indexOf(sid) + 1}
        </span>
      ),
    },
    {
      key: "id",
      label: "ID",
      width: "w-28",
      cardRole: "meta",
      render: (sid) => <RefChip refId={sid} />,
    },
    {
      key: "historia",
      label: "Historia",
      cardRole: "title",
      render: (sid) => {
        const s = storyById.get(sid);
        return (
          <span className="line-clamp-2">{s?.goal ?? s?.statement ?? "—"}</span>
        );
      },
    },
    {
      key: "prioridad",
      label: "Prioridad",
      width: "w-28",
      cardRole: "badge",
      render: (sid) => <MoscowBadge priority={storyById.get(sid)?.priority} />,
    },
    {
      key: "puntos",
      label: "Puntos",
      width: "w-20",
      numeric: true,
      render: (sid) => storyById.get(sid)?.story_points ?? "—",
    },
    {
      key: "asignado",
      label: "Asignado a",
      width: "w-52",
      render: (sid) => (
        <AssigneeSelect
          storyId={sid}
          team={team}
          member={assigneeOf.get(sid)}
          inherited={sourceOf.get(sid) === "sprint"}
          readOnly={!puedeEditar}
          busy={assigningId === sid}
          onAssign={onAssign}
        />
      ),
    },
  ];

  const sheetQuestions = a.questions_for_po.map(
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
    <ScrumValidationControls
      readOnly={!puedeEditar}
      jobId={job.job_id}
      targetId={id}
      status={statusOf(id)}
      respuesta={respuestaOf(id)}
      onChanged={() => {
        void reloadSummary();
        onAnswered?.();
      }}
    />
  );

  /** Historias visibles: filtro por responsable + buscador local. */
  const storiesFor = (query: string, priority?: MoscowPriority) =>
    filterByQuery(
      query,
      a.stories.filter(
        (s) =>
          matchesPersonFilter(s.id, personFilter, assigneeOf) &&
          (!priority || s.priority === priority),
      ),
      STORY_TEXT,
    );

  const storiesTab = (
    id: string,
    label: string,
    priority?: MoscowPriority,
  ) => ({
    id,
    label,
    count: priority
      ? a.stories.filter((s) => s.priority === priority).length
      : a.stories.length,
    matchCount: (q: string) => storiesFor(q, priority).length,
    // Las pestañas MoSCoW filtran "Todas": en el PDF bastaría con esa, y
    // repetirlas duplicaría las 31 historias cuatro veces.
    printSkip: priority !== undefined,
    render: (ctx: PanelRenderCtx) => (
      <StoryList
        stories={storiesFor(ctx.query, priority)}
        ctx={ctx}
        team={team}
        assigneeOf={assigneeOf}
        sourceOf={sourceOf}
        expanded={expandedStories}
        onToggle={toggleStory}
        onAssign={onAssign}
        assigningId={assigningId}
        readOnly={!puedeEditar}
      />
    ),
  });

  const sections: HubSection[] = [
    {
      id: "backlog",
      title: "Backlog",
      printTitle: "Backlog de producto",
      icon: <ListOrdered />,
      count: a.product_backlog.ordered_story_ids.length,
      metrics: `${plural(a.product_backlog.ordered_story_ids.length, "historia")} · ${a.product_backlog.method}`,
      insight: (
        <span>
          {plural(a.metrics.points_total, "punto")} · {mustCount} must
        </span>
      ),
      render: ({ query, forPrint }) => {
        const rows = backlogRows(forPrint ? "" : query);
        return (
          <>
            <DataTable
              columns={backlogColumns(rows)}
              rows={rows}
              rowKey={(sid) => sid}
              zebra
              empty={
                personFilter
                  ? "Ninguna historia del backlog coincide con ese responsable."
                  : query
                    ? "Nada coincide con la búsqueda."
                    : "Backlog vacío."
              }
            />
            {a.product_backlog.rationale && (
              <p className="prose-measure mt-2 text-xs text-muted-foreground">
                {a.product_backlog.rationale}
              </p>
            )}
          </>
        );
      },
    },

    {
      id: "sprints",
      title: "Sprints",
      icon: <Layers />,
      count: a.sprints.length,
      metrics: `${plural(a.sprints.length, "sprint")} · ${a.metrics.points_total} pts`,
      urgent: a.unassigned_story_ids.length > 0,
      urgentLabel:
        a.unassigned_story_ids.length > 0
          ? String(a.unassigned_story_ids.length)
          : undefined,
      insight:
        a.unassigned_story_ids.length > 0 ? (
          <span>
            {plural(a.unassigned_story_ids.length, "historia")} fuera de sprint
          </span>
        ) : (
          <span>Todas las historias estimadas quedaron asignadas</span>
        ),
      render: ({ query, forPrint }) => {
        const q = forPrint ? "" : query;
        const sprints = filterByQuery(q, a.sprints, (sp) => [
          sp.id,
          sp.goal,
          ...sp.story_ids,
        ]);
        return (
          <div className="space-y-3">
            {sprints.length === 0 && (
              <EmptyHint warn={!q}>
                {q ? "Ningún sprint coincide." : "Sin sprints."}
              </EmptyHint>
            )}
            {sprints.map((sp) => (
              <div
                key={sp.id}
                id={`ref-${sp.id}`}
                className="print-atom rounded-lg border p-3"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <IdTag id={sp.id} />
                  <Badge variant="outline" className="font-mono tabular-nums">
                    {sp.total_points}/{sp.capacity_points} pts
                  </Badge>
                  <span className="text-sm text-muted-foreground">{sp.goal}</span>
                  <span className="ml-auto print:hidden">
                    <SprintAssigneeSelect
                      sprintId={sp.id}
                      team={team}
                      member={sprintAssigneeOf.get(sp.id)}
                      readOnly={!puedeEditar}
                      busy={assigningId === sp.id}
                      onAssign={onAssignSprint}
                    />
                  </span>
                </div>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {sp.story_ids.map((sid) => (
                    <span key={sid} className="inline-flex items-center gap-1">
                      <RefChip refId={sid} />
                      {/* Avatar compacto: quién lleva cada historia del sprint. */}
                      {assigneeOf.get(sid) && (
                        <AssigneeBadge member={assigneeOf.get(sid)} compact />
                      )}
                    </span>
                  ))}
                </div>
                <SprintLoad
                  loads={loadsOfSprint(sp.story_ids)}
                  capacityPoints={sp.capacity_points}
                  unassignedPoints={unassignedPointsOf(sp.story_ids)}
                />
              </div>
            ))}
            {a.unassigned_story_ids.length > 0 && (
              <div className="rounded-lg border border-amber-300 bg-amber-50/50 p-3">
                <GroupLabel count={a.unassigned_story_ids.length}>
                  <span className="text-amber-700">⚠ Fuera de sprint</span>
                </GroupLabel>
                <div className="flex flex-wrap gap-1.5">
                  {a.unassigned_story_ids.map((sid) => (
                    <RefChip key={sid} refId={sid} />
                  ))}
                </div>
              </div>
            )}
          </div>
        );
      },
    },

    {
      id: "historias",
      title: "Historias",
      printTitle: "Historias de usuario",
      icon: <ListChecks />,
      count: a.stories.length,
      metrics: `${a.stories.length} · ${estimated} estimadas`,
      urgent: checks ? !checks.must_should_estimated : false,
      insight:
        unestimated > 0 ? (
          <span>{plural(unestimated, "historia")} sin estimar</span>
        ) : (
          <span>Todas estimadas · criterios en Gherkin</span>
        ),
      tabs: [
        storiesTab("todas", "Todas"),
        storiesTab("must", "Must", "must"),
        storiesTab("should", "Should", "should"),
        storiesTab("could", "Could", "could"),
        storiesTab("wont", "Won't", "wont"),
      ],
    },

    {
      id: "epicas",
      title: "Épicas",
      icon: <Hash />,
      count: a.epics.length,
      metrics: plural(a.epics.length, "épica"),
      insight: (
        <span className="line-clamp-2">
          {a.epics.map((e) => e.title).join(" · ") || "Sin épicas"}
        </span>
      ),
      render: ({ query, forPrint }) => {
        const q = forPrint ? "" : query;
        const epics = filterByQuery(q, a.epics, (e) => [
          e.id,
          e.title,
          e.description,
          ...e.source_refs,
          ...e.story_ids,
        ]);
        if (epics.length === 0)
          return (
            <EmptyHint warn={!q}>
              {q ? "Ninguna épica coincide." : "Sin épicas."}
            </EmptyHint>
          );
        return (
          <div className="space-y-2">
            {epics.map((e) => (
              <div
                key={e.id}
                id={`ref-${e.id}`}
                className="print-atom rounded-lg border p-3"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <IdTag id={e.id} />
                  <span className="text-sm font-medium">{e.title}</span>
                  <ConfidenceBadge value={e.confidence} />
                </div>
                {e.description && (
                  <p className="mt-1 text-xs text-muted-foreground">
                    {e.description}
                  </p>
                )}
                <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
                  <span className="inline-flex flex-wrap items-center gap-1">
                    origen:{" "}
                    {e.source_refs.map((r) => (
                      <RefChip key={r} refId={r} />
                    ))}
                  </span>
                  <span className="inline-flex flex-wrap items-center gap-1">
                    historias:{" "}
                    {e.story_ids.map((r) => (
                      <RefChip key={r} refId={r} />
                    ))}
                  </span>
                </div>
              </div>
            ))}
          </div>
        );
      },
    },

    {
      id: "preguntas",
      title: "Preguntas al PO",
      printTitle: "Preguntas al Product Owner",
      icon: <MessagesSquare />,
      count: a.questions_for_po.length,
      metrics: `${a.questions_for_po.length} · ${plural(blockingTotal, "bloqueante")}`,
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
            · {answered} respondidas
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
          ? a.questions_for_po
          : onlyBlocking
            ? a.questions_for_po.filter((q) => q.blocking)
            : a.questions_for_po;
        const items = filterByQuery(forPrint ? "" : query, base, (q) => [
          q.id,
          q.question,
          q.reason,
          q.linked_to_ref,
        ]);
        if (items.length === 0) {
          return (
            <EmptyHint warn={false}>
              {query
                ? "Ninguna pregunta coincide con la búsqueda."
                : onlyBlocking
                  ? "Sin preguntas bloqueantes."
                  : "Sin preguntas al PO."}
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
      id: "analisis",
      title: "Análisis",
      icon: <AlertTriangle />,
      count: a.analysis.risks.length + a.analysis.observations.length,
      metrics: plural(
        a.analysis.risks.length + a.analysis.observations.length,
        "hallazgo",
      ),
      urgent: checks ? !checks.coverage_met : false,
      insight: (
        <span>
          Cobertura RF {Math.round(cov.coverage_ratio * 100)}% ·{" "}
          {plural(a.analysis.risks.length, "riesgo")}
        </span>
      ),
      tabs: [
        {
          id: "cobertura",
          label: "Cobertura",
          render: () => (
            <div className="rounded-lg border p-3 text-sm">
              <GroupLabel>Cobertura de requisitos funcionales</GroupLabel>
              <p>
                {cov.requirements_covered} / {cov.requirements_total} cubiertos (
                {Math.round(cov.coverage_ratio * 100)}%)
              </p>
              {cov.uncovered_requirement_refs.length > 0 ? (
                <p className="mt-1 inline-flex flex-wrap items-center gap-1 text-amber-700">
                  ⚠ No cubiertos:{" "}
                  {cov.uncovered_requirement_refs.map((r) => (
                    <RefChip key={r} refId={r} />
                  ))}
                </p>
              ) : (
                <p className="mt-1 text-xs text-emerald-700">
                  Todos los RF quedaron cubiertos.
                </p>
              )}
            </div>
          ),
        },
        {
          id: "riesgos",
          label: "Riesgos",
          count: a.analysis.risks.length,
          matchCount: (q) =>
            filterByQuery(q, a.analysis.risks, (r) => [
              r.id,
              r.description,
              r.severity,
            ]).length,
          render: ({ query, forPrint }) => {
            const items = filterByQuery(
              forPrint ? "" : query,
              a.analysis.risks,
              (r) => [r.id, r.description, r.severity],
            );
            if (items.length === 0)
              return <EmptyHint warn={false}>Sin riesgos.</EmptyHint>;
            return (
              <DataList>
                {items.map((r) => (
                  <DataRow
                    key={r.id}
                    id={r.id}
                    right={
                      <>
                        <Badge variant="outline">{r.severity}</Badge>
                        <IdTag id={r.id} />
                      </>
                    }
                  >
                    {r.description}
                  </DataRow>
                ))}
              </DataList>
            );
          },
        },
        {
          id: "observaciones",
          label: "Observaciones",
          count: a.analysis.observations.length,
          matchCount: (q) =>
            filterByQuery(q, a.analysis.observations, (o) => [
              o.id,
              o.description,
              o.reason,
            ]).length,
          render: ({ query, forPrint }) => {
            const items = filterByQuery(
              forPrint ? "" : query,
              a.analysis.observations,
              (o) => [o.id, o.description, o.reason],
            );
            if (items.length === 0)
              return <EmptyHint warn={false}>Sin observaciones.</EmptyHint>;
            return (
              <DataList>
                {items.map((o) => (
                  <DataRow key={o.id} id={o.id} right={<IdTag id={o.id} />}>
                    {o.description}
                    {o.reason ? (
                      <span className="text-muted-foreground"> — {o.reason}</span>
                    ) : null}
                  </DataRow>
                ))}
              </DataList>
            );
          },
        },
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
          kind="Plan Scrum"
          title="Plan ágil"
          subtitle="Épicas, historias, criterios de aceptación, estimaciones, backlog priorizado y plan de sprints."
          version="1.0.0"
          stats={[
            { label: "historias", value: String(a.metrics.stories_total) },
            { label: "puntos", value: String(a.metrics.points_total) },
            { label: "sprints", value: String(a.metrics.sprints_total) },
            {
              label: "cobertura",
              value: `${Math.round(a.metrics.coverage * 100)}%`,
            },
          ]}
        />
        <PrintFooter title="Plan Scrum" />

        {/* Barra superior de afinamiento + semáforo */}
        <div className="sticky top-0 z-10 border-b bg-background/95 px-6 py-4 backdrop-blur print:hidden">
          {/* (a) Identidad: qué plan es, de qué EF sale y en qué estado está. */}
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2 text-sm">
            <span className="font-heading font-semibold">Plan Scrum v1.0.0</span>
            <Badge variant="outline">
              {job.parent_job_id ? "v2 · afinamiento" : "v1 · original"}
            </Badge>
            {job.parent_job_id && (
              <Link
                href={`/agents/scrum/jobs/${job.parent_job_id}`}
                className="text-xs text-muted-foreground underline-offset-2 hover:text-primary hover:underline"
              >
                ver original (<Mono>{job.parent_job_id}</Mono>)
              </Link>
            )}
            {job.input_job_id && (
              <Link
                href={`/agents/ef/jobs/${job.input_job_id}`}
                className="text-xs text-muted-foreground underline-offset-2 hover:text-primary hover:underline"
              >
                EF de origen (<Mono>{job.input_job_id}</Mono>)
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
                ? "Listo para el Agente Arquitectura"
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

            {/* Filtro por responsable: la asignación es una lectura transversal del
                plan, así que vive en la barra y afecta backlog e historias. */}
            {team.length > 0 && (
              <label className="inline-flex items-center gap-1.5 text-xs text-meta-foreground print:hidden">
                Ver historias de
                <NativeSelect
                  value={personFilter}
                  onChange={(e) => setPersonFilter(e.target.value)}
                  aria-label="Filtrar historias por responsable"
                  className="h-8 max-w-[12rem] text-xs"
                >
                  <option value="">Todas</option>
                  <option value={SIN_ASIGNAR}>Sin asignar</option>
                  {team.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.full_name}
                    </option>
                  ))}
                </NativeSelect>
              </label>
            )}

            {/* Acciones agrupadas: preguntas | exportes | regenerar. */}
            <div className="ml-auto">
              <HeaderActions>
              {puedeEditar && a.questions_for_po.length > 0 && (
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
                variant="ghost"
                size="sm"
                className="gap-1.5"
                onClick={() => doExport("csv")}
              >
                <FileDown className="h-3.5 w-3.5" />
                ClickUp CSV
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="gap-1.5"
                onClick={() => doExport("json")}
              >
                <FileDown className="h-3.5 w-3.5" />
                JSON
              </Button>
              {/*
                Envío directo a ClickUp: VISIBLE pero deshabilitado. Está aquí a
                propósito — comunica que la asignación que el equipo hace hoy no se
                va a perder cuando llegue la API. Ocultarlo dejaría la duda de si
                asignar sirve para algo. El `<span>` envuelve al botón porque un
                elemento `disabled` no emite eventos de ratón y el tooltip no se
                mostraría.
              */}
              <Tooltip>
                <TooltipTrigger
                  render={
                    <span className="inline-flex">
                      <Button
                        variant="outline"
                        size="sm"
                        className="gap-1.5"
                        disabled
                      >
                        <Send className="h-3.5 w-3.5" />
                        Enviar a ClickUp
                      </Button>
                    </span>
                  }
                />
                <TooltipContent>
                  Disponible en la próxima versión — las asignaciones ya quedarán
                  vinculadas.
                </TooltipContent>
              </Tooltip>
              <Button
                variant="outline"
                size="sm"
                className="gap-1.5"
                onClick={() =>
                  download(
                    JSON.stringify(a, null, 2),
                    `scrum-artifact-${job.job_id}.json`,
                    "application/json",
                  )
                }
              >
                <Download className="h-3.5 w-3.5" />
                Artefacto
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
                        Se creará un plan hijo reinyectando las respuestas del
                        Product Owner y se ejecutará el modelo real.
                      </DialogDescription>
                    </DialogHeader>
                    <div className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800">
                      Costo estimado: ~${a.metrics.cost.toFixed(4)} (similar al plan
                      anterior). Esta acción consume tokens de la API.
                    </div>
                    <DialogFooter>
                      <Button onClick={doRefine} disabled={refining || !canRefine}>
                        {refining ? "Regenerando…" : "Confirmar y regenerar"}
                      </Button>
                    </DialogFooter>
                  </DialogContent>
                  </Dialog>
                </ActionGroup>
              )}
              </HeaderActions>
            </div>
          </div>
          {checks && (
            <div className="mt-2.5 flex flex-wrap gap-2">
              <StatusPill ok={checks.no_blocking_questions} label="Sin bloqueantes PO" />
              <StatusPill ok={checks.must_should_estimated} label="Must/should estimadas" />
              <StatusPill ok={checks.coverage_met} label="Cobertura RF" />
              <StatusPill ok={checks.no_must_unassigned} label="Sin must sin asignar" />
            </div>
          )}
        </div>

        {/* (b) Mini-stats, con el estado separado a la derecha. */}
        <div className="border-b px-6 py-5 print:hidden">
          <div className="flex flex-wrap items-center gap-x-8 gap-y-4">
            <StatRow>
              <Stat
                icon={<ListChecks />}
                value={a.metrics.stories_total}
                label="historias"
              />
              <Stat icon={<Hash />} value={a.metrics.points_total} label="puntos" />
              <Stat
                icon={<Layers />}
                value={a.metrics.sprints_total}
                label="sprints"
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

        {/* EL HUB */}
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
                      ? "Plan listo para el Agente Arquitectura"
                      : "Sin preguntas bloqueantes del PO pendientes"}
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {ready
                      ? "El semáforo compuesto está en verde."
                      : "Aún faltan otras condiciones del semáforo (cobertura, estimaciones o asignación)."}
                  </p>
                </div>
              </div>
            </div>
          )}

          <HubGrid>
            {sections.map((s) => (
              <HubCard
                key={s.id}
                module="scrum"
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

        <ArtifactPanel hub={hub} sections={sections} module="scrum" />
        <ArtifactPrintDoc sections={sections} active={printMode} />
      </div>
    </ArtifactNavProvider>
  );
}

// --- subcomponentes ----------------------------------------------------------

/**
 * Historias de usuario: fila-tarjeta con badges de dominio, trazabilidad al EF,
 * responsable y criterios de aceptación plegados. Los criterios se despliegan al
 * imprimir, al buscar (el término puede estar dentro) y al llegar por un chip
 * `AC-…` (si no, no habría nada que resaltar).
 */
function StoryList({
  stories,
  ctx,
  team,
  assigneeOf,
  sourceOf,
  expanded,
  onToggle,
  onAssign,
  assigningId,
  readOnly,
}: {
  stories: Story[];
  ctx: PanelRenderCtx;
  team: TeamMember[];
  assigneeOf: Map<string, TeamMember | undefined>;
  sourceOf: Map<string, "story" | "sprint">;
  expanded: Set<string>;
  onToggle: (id: string) => void;
  onAssign: (storyId: string, userId: string | null) => void;
  assigningId: string | null;
  readOnly: boolean;
}) {
  if (stories.length === 0) {
    return (
      <EmptyHint>
        {ctx.query
          ? "Ninguna historia coincide con la búsqueda."
          : "Ninguna historia en este grupo."}
      </EmptyHint>
    );
  }
  const expandAll =
    ctx.forPrint || !!ctx.query || (ctx.refId?.startsWith("AC-") ?? false);

  return (
    <div className="space-y-3">
      {stories.map((s) => {
        const open = expandAll || expanded.has(s.id);
        return (
          <div
            key={s.id}
            id={`ref-${s.id}`}
            className="print-atom rounded-lg border p-3"
          >
            <div className="flex flex-wrap items-center gap-2">
              <IdTag id={s.id} />
              <MoscowBadge priority={s.priority} />
              <PointsBadge points={s.story_points} />
              {s.epic_ref && (
                <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                  épica <RefChip refId={s.epic_ref} />
                </span>
              )}
              <ConfidenceBadge value={s.confidence} />
              {/* Asignar a: alineado a la derecha para no competir con los
                  badges del dominio. */}
              <span className="ml-auto print:hidden">
                <AssigneeSelect
                  storyId={s.id}
                  team={team}
                  member={assigneeOf.get(s.id)}
                  inherited={sourceOf.get(s.id) === "sprint"}
                  readOnly={readOnly}
                  busy={assigningId === s.id}
                  onAssign={onAssign}
                />
              </span>
              {/* En impresión el responsable se ve como texto. */}
              <span className="ml-auto hidden print:inline">
                {assigneeOf.get(s.id)?.full_name ?? "sin asignar"}
              </span>
            </div>
            <p className="mt-1.5 text-sm font-medium">{s.statement}</p>

            {/* Trazabilidad al EF */}
            <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
              <span className="inline-flex flex-wrap items-center gap-1">
                RF:{" "}
                {s.source_refs.requirement_refs.map((r) => (
                  <RefChip key={r} refId={r} />
                ))}
              </span>
              {s.source_refs.rule_refs.length > 0 && (
                <span className="inline-flex flex-wrap items-center gap-1">
                  reglas:{" "}
                  {s.source_refs.rule_refs.map((r) => (
                    <RefChip key={r} refId={r} />
                  ))}
                </span>
              )}
              {s.dependencies.length > 0 && (
                <span className="inline-flex flex-wrap items-center gap-1">
                  depende de:{" "}
                  {s.dependencies.map((r) => (
                    <RefChip key={r} refId={r} />
                  ))}
                </span>
              )}
            </div>

            {/* Criterios de aceptación (Gherkin) */}
            {s.acceptance_criteria.length > 0 ? (
              <div className="mt-2">
                <button
                  type="button"
                  onClick={() => onToggle(s.id)}
                  aria-expanded={open}
                  className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground print:hidden"
                >
                  <ChevronRight
                    className={cn(
                      "h-3.5 w-3.5 transition-transform duration-200",
                      open && "rotate-90",
                    )}
                  />
                  Criterios de aceptación ({s.acceptance_criteria.length})
                </button>
                <div
                  className={cn(
                    "grid transition-[grid-template-rows] duration-200 ease-out print:grid-rows-[1fr]",
                    open ? "grid-rows-[1fr]" : "grid-rows-[0fr]",
                  )}
                >
                  <div className="overflow-hidden print:overflow-visible">
                    <div className="mt-2 space-y-1.5">
                      {s.acceptance_criteria.map((c) => (
                        <div
                          key={c.id}
                          id={`ref-${c.id}`}
                          className="rounded-lg border bg-muted/30 p-2.5 text-xs"
                        >
                          <div className="mb-1">
                            <IdTag id={c.id} />
                          </div>
                          {c.format === "gherkin" ? (
                            <span>
                              <b className="text-foreground">Dado</b> {c.given}{" "}
                              <b className="text-foreground">cuando</b> {c.when}{" "}
                              <b className="text-foreground">entonces</b> {c.then}
                            </span>
                          ) : (
                            <span>{c.text}</span>
                          )}{" "}
                          {c.source_refs.map((r) => (
                            <RefChip key={r} refId={r} className="ml-1" />
                          ))}
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <div className="mt-2">
                <EmptyHint>Sin criterios de aceptación.</EmptyHint>
              </div>
            )}

            {s.estimation_rationale && (
              <p className="mt-1.5 inline-flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                Estimación sugerida: {s.estimation_rationale}
                <ConfidenceBadge value={s.estimation_confidence} />
              </p>
            )}
          </div>
        );
      })}
    </div>
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
