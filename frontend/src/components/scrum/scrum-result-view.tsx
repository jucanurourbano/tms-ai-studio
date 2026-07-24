"use client";

import {
  ChevronRight,
  Coins,
  Download,
  DollarSign,
  FileDown,
  Hash,
  Layers,
  ListChecks,
  MessagesSquare,
  Printer,
  Target,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { AudienceBadge, ConfidenceBadge, JobStatusBadge, Mono } from "@/components/ef/badges";
import {
  ArtifactIndexPanel,
  type IndexSection,
} from "@/components/artifact/artifact-index";
import { ArtifactSection } from "@/components/artifact/artifact-section";
import {
  QuestionSheet,
  type SheetQuestion,
} from "@/components/artifact/question-sheet";
import {
  DataList,
  DataRow,
  EmptyHint,
  GroupLabel,
  IdTag,
  PrintCover,
  PrintFooter,
  PrintToc,
  PrintValidationState,
  RefChip,
  Stat,
  StatRow,
  StatusPill,
} from "@/components/artifact/primitives";
import { ArtifactSkeleton } from "@/components/artifact/artifact-skeleton";
import { BackToTop } from "@/components/artifact/back-to-top";
import { ScrumValidationControls } from "@/components/scrum/validation-controls";
import { Badge } from "@/components/ui/badge";
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
import type { QuestionStatus } from "@/lib/types/ef";
import type {
  MoscowPriority,
  ScrumArtifact,
  ScrumJobDetail,
  ScrumValidationSummary,
  Story,
} from "@/lib/types/scrum";
import { useDisclosure } from "@/lib/use-disclosure";
import { usePersistentState } from "@/lib/use-persistent-state";
import { usePrintExpand } from "@/lib/use-print-expand";
import { cn } from "@/lib/utils";

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

// --- componente principal ----------------------------------------------------

export function ScrumResultView({ job }: { job: ScrumJobDetail }) {
  const router = useRouter();
  const [artifact, setArtifact] = useState<ScrumArtifact | null>(null);
  const [summary, setSummary] = useState<ScrumValidationSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [onlyBlocking, setOnlyBlocking] = useState(false);
  const [refining, setRefining] = useState(false);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [expandedStories, setExpandedStories] = useState<Set<string>>(new Set());
  const [indexCollapsed, setIndexCollapsed] = usePersistentState(
    "artifact:index-collapsed",
    false,
  );
  const disc = useDisclosure(2);
  const { printMode, printNow } = usePrintExpand();

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

  const reloadSummary = useCallback(async (): Promise<ScrumValidationSummary | null> => {
    try {
      const s = await scrumApi.getValidationSummary(job.job_id);
      setSummary(s);
      return s;
    } catch {
      return null;
    }
  }, [job.job_id]);

  const scrollToRef = useCallback((id: string) => {
    const el = document.getElementById(`ref-${id}`);
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    el.classList.add("ref-highlight");
    window.setTimeout(() => el.classList.remove("ref-highlight"), 1600);
  }, []);

  const handlePoAnswered = useCallback(
    async (answeredId: string) => {
      const s = await reloadSummary();
      if (!s || !artifact) return;
      const statusIn = (id: string) =>
        s.validations.find((v) => v.target_id === id)?.status ?? "pendiente";
      const next = artifact.questions_for_po.find(
        (q) => q.blocking && q.id !== answeredId && statusIn(q.id) === "pendiente",
      );
      if (next) scrollToRef(next.id);
    },
    [reloadSummary, artifact, scrollToRef],
  );

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
  const questions = onlyBlocking
    ? a.questions_for_po.filter((q) => q.blocking)
    : a.questions_for_po;
  const cov = a.analysis.coverage;
  const canRefine = answered >= 1;

  const blockingTotal = a.questions_for_po.filter((q) => q.blocking).length;
  const blockingRemaining = a.questions_for_po.filter(
    (q) => q.blocking && statusOf(q.id) === "pendiente",
  ).length;
  const blockingDone = blockingTotal > 0 && blockingRemaining === 0;
  const indexSections: IndexSection[] = [
    {
      id: "sec-backlog",
      label: "Backlog",
      count: a.product_backlog.ordered_story_ids.length,
    },
    { id: "sec-sprints", label: "Sprints", count: a.sprints.length },
    { id: "sec-stories", label: "Historias", count: a.stories.length },
    { id: "sec-epics", label: "Épicas", count: a.epics.length },
    {
      id: "sec-questions",
      label: "Preguntas al PO",
      count: a.questions_for_po.length,
      meta: `${blockingTotal} bloq.`,
    },
    {
      id: "sec-analysis",
      label: "Análisis",
      count: a.analysis.risks.length + a.analysis.observations.length,
    },
  ];

  return (
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
          { label: "cobertura", value: `${Math.round(a.metrics.coverage * 100)}%` },
        ]}
      />
      <PrintToc
        items={[
          "Backlog de producto",
          "Sprints",
          "Historias de usuario",
          "Épicas",
          "Preguntas al Product Owner",
          "Análisis",
        ]}
      />
      <PrintFooter title="Plan Scrum" />

      {/* Barra superior de afinamiento + semáforo */}
      <div className="sticky top-0 z-10 border-b bg-background/95 px-6 py-3 backdrop-blur print:hidden">
        <div className="flex flex-wrap items-center gap-3 text-sm">
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
          <span className="text-xs text-muted-foreground">{answered} respondidas</span>
          <span
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs",
              ready
                ? "border-emerald-300 bg-emerald-50 text-emerald-700"
                : "border-slate-300 bg-slate-50 text-slate-600",
            )}
          >
            <span
              className={cn(
                "h-2 w-2 rounded-full",
                ready ? "bg-emerald-500" : "bg-slate-400",
              )}
            />
            {ready ? "Listo para el Agente Arquitectura" : "Pendiente de afinamiento"}
          </span>

          <div className="ml-auto flex flex-wrap gap-2">
            {a.questions_for_po.length > 0 && (
              <Button
                variant="outline"
                size="sm"
                className="gap-1.5"
                onClick={() => setSheetOpen(true)}
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
              variant="outline"
              size="sm"
              className="gap-1.5"
              onClick={printNow}
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
                    Se creará un plan hijo reinyectando las respuestas del Product
                    Owner y se ejecutará el modelo real.
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

      {/* Cabecera: estado y mini-stats */}
      <div className="border-b px-6 py-4">
        <div className="mb-3">
          <JobStatusBadge status={job.status} />
        </div>
        <StatRow>
          <Stat icon={<ListChecks />} value={a.metrics.stories_total} label="historias" />
          <Stat icon={<Hash />} value={a.metrics.points_total} label="puntos" />
          <Stat icon={<Layers />} value={a.metrics.sprints_total} label="sprints" />
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
      </div>

      {/* Dos columnas: índice (plegable) + contenido */}
      <div
        className={cn(
          "grid grid-cols-1 gap-6 px-4 py-5 md:px-6 print:block!",
          indexCollapsed
            ? "md:grid-cols-[2.75rem_1fr]"
            : "md:grid-cols-[13rem_1fr]",
        )}
      >
        <div className="md:sticky md:top-28 md:self-start print:hidden">
          <ArtifactIndexPanel
            sections={indexSections}
            collapsed={indexCollapsed}
            onToggle={() => setIndexCollapsed((v) => !v)}
            onNavigate={disc.openOnly}
            openIds={disc.openIds}
          />
        </div>

        <div className="min-w-0 space-y-6">
          {/* Banner de éxito */}
          {blockingDone && (
            <div
              className={cn(
                "rounded-xl border p-4 print:hidden",
                ready
                  ? "border-emerald-300 bg-emerald-50"
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

          {/* 1. Backlog — tabla real */}
          <ArtifactSection
            id="sec-backlog"
            index="1"
            title={`Backlog de producto (${a.product_backlog.method})`}
            count={a.product_backlog.ordered_story_ids.length}
            open={disc.isOpen("sec-backlog")}
            onToggle={() => disc.toggle("sec-backlog")}
            forceRender={printMode}
            preview={
              <span>
                {a.product_backlog.ordered_story_ids.length} historias priorizadas
                por {a.product_backlog.method}
              </span>
            }
          >
            {a.product_backlog.ordered_story_ids.length > 0 ? (
              <div className="overflow-x-auto rounded-lg border">
                <table className="w-full border-collapse text-sm">
                  <thead className="sticky top-0 z-[1] bg-muted/70 text-[11px] uppercase tracking-wide text-muted-foreground backdrop-blur">
                    <tr className="[&>th]:px-3 [&>th]:py-2 [&>th]:font-semibold">
                      <th className="w-10 text-right">#</th>
                      <th className="w-24 text-left">ID</th>
                      <th className="text-left">Historia</th>
                      <th className="w-24 text-left">Prioridad</th>
                      <th className="w-20 text-right">Puntos</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/60">
                    {a.product_backlog.ordered_story_ids.map((sid, i) => {
                      const s = storyById.get(sid);
                      return (
                        <tr
                          key={sid}
                          className="odd:bg-muted/20 hover:bg-primary/[0.04] [&>td]:px-3 [&>td]:py-2 [&>td]:align-top"
                        >
                          <td className="text-right font-mono text-[11px] tabular-nums text-muted-foreground/70">
                            {i + 1}
                          </td>
                          <td>
                            <RefChip refId={sid} />
                          </td>
                          <td className="min-w-0">
                            <span className="line-clamp-2">
                              {s?.goal ?? s?.statement ?? "—"}
                            </span>
                          </td>
                          <td>
                            <MoscowBadge priority={s?.priority} />
                          </td>
                          <td className="text-right font-mono tabular-nums">
                            {s?.story_points ?? "—"}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <EmptyHint>Backlog vacío.</EmptyHint>
            )}
            {a.product_backlog.rationale && (
              <p className="mt-2 text-xs text-muted-foreground">
                {a.product_backlog.rationale}
              </p>
            )}
          </ArtifactSection>

          {/* 2. Sprints */}
          <ArtifactSection
            id="sec-sprints"
            index="2"
            title="Sprints"
            count={a.sprints.length}
            open={disc.isOpen("sec-sprints")}
            onToggle={() => disc.toggle("sec-sprints")}
            forceRender={printMode}
            preview={
              <span>
                {a.metrics.points_total} puntos en {a.sprints.length} sprint
                {a.sprints.length !== 1 ? "s" : ""}
                {a.unassigned_story_ids.length > 0 ? (
                  <span className="text-amber-700">
                    {" "}
                    · {a.unassigned_story_ids.length} sin asignar
                  </span>
                ) : null}
              </span>
            }
          >
            <div className="space-y-3">
              {a.sprints.map((sp) => (
                <div key={sp.id} className="print-atom rounded-lg border p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <IdTag id={sp.id} />
                    <Badge variant="outline" className="font-mono tabular-nums">
                      {sp.total_points}/{sp.capacity_points} pts
                    </Badge>
                    <span className="text-sm text-muted-foreground">{sp.goal}</span>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {sp.story_ids.map((sid) => (
                      <RefChip key={sid} refId={sid} />
                    ))}
                  </div>
                </div>
              ))}
              {a.unassigned_story_ids.length > 0 ? (
                <div className="rounded-lg border border-amber-300 bg-amber-50/50 p-3">
                  <GroupLabel count={a.unassigned_story_ids.length}>
                    <span className="text-amber-700">⚠ Sin asignar</span>
                  </GroupLabel>
                  <div className="flex flex-wrap gap-1.5">
                    {a.unassigned_story_ids.map((sid) => (
                      <RefChip key={sid} refId={sid} />
                    ))}
                  </div>
                </div>
              ) : (
                <p className="text-xs text-muted-foreground">
                  Todas las historias estimadas quedaron asignadas.
                </p>
              )}
            </div>
          </ArtifactSection>

          {/* 3. Historias */}
          <ArtifactSection
            id="sec-stories"
            index="3"
            title="Historias de usuario"
            count={a.stories.length}
            open={disc.isOpen("sec-stories")}
            onToggle={() => disc.toggle("sec-stories")}
            forceRender={printMode}
            preview={
              <span>
                {a.stories.filter((s) => s.story_points != null).length} de{" "}
                {a.stories.length} estimadas · con criterios de aceptación Gherkin
              </span>
            }
          >
            <div className="space-y-3">
              {a.stories.map((s) => (
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

                  {/* Criterios de aceptación (Gherkin) — plegados por defecto */}
                  {s.acceptance_criteria.length > 0 ? (
                    <div className="mt-2">
                      <button
                        type="button"
                        onClick={() => toggleStory(s.id)}
                        aria-expanded={expandedStories.has(s.id)}
                        className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
                      >
                        <ChevronRight
                          className={cn(
                            "h-3.5 w-3.5 transition-transform duration-200",
                            expandedStories.has(s.id) && "rotate-90",
                          )}
                        />
                        Criterios de aceptación ({s.acceptance_criteria.length})
                      </button>
                      <div
                        className={cn(
                          "grid transition-[grid-template-rows] duration-200 ease-in-out",
                          expandedStories.has(s.id)
                            ? "grid-rows-[1fr]"
                            : "grid-rows-[0fr]",
                        )}
                      >
                        <div className="overflow-hidden">
                          <div className="mt-2 space-y-1.5">
                            {s.acceptance_criteria.map((c) => (
                              <div
                                key={c.id}
                                className="rounded-lg border bg-muted/30 p-2.5 text-xs"
                              >
                                <div className="mb-1">
                                  <IdTag id={c.id} />
                                </div>
                                {c.format === "gherkin" ? (
                                  <span>
                                    <b className="text-foreground">Dado</b> {c.given}{" "}
                                    <b className="text-foreground">cuando</b> {c.when}{" "}
                                    <b className="text-foreground">entonces</b>{" "}
                                    {c.then}
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
              ))}
            </div>
          </ArtifactSection>

          {/* 4. Épicas */}
          <ArtifactSection
            id="sec-epics"
            index="4"
            title="Épicas"
            count={a.epics.length}
            open={disc.isOpen("sec-epics")}
            onToggle={() => disc.toggle("sec-epics")}
            forceRender={printMode}
            preview={
              <span className="line-clamp-2">
                {a.epics.map((e) => e.title).join(" · ") || "Sin épicas"}
              </span>
            }
          >
            <div className="space-y-2">
              {a.epics.map((e) => (
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
          </ArtifactSection>

          {/* 5. Preguntas al PO */}
          <ArtifactSection
            id="sec-questions"
            index="5"
            title="Preguntas al Product Owner"
            count={a.questions_for_po.length}
            meta={`${blockingTotal} bloq.`}
            open={disc.isOpen("sec-questions")}
            onToggle={() => disc.toggle("sec-questions")}
            forceRender={printMode}
            preview={
              <span>
                {blockingRemaining > 0 ? (
                  <span className="font-medium text-red-600">
                    {blockingRemaining} bloqueante
                    {blockingRemaining !== 1 ? "s" : ""} sin responder
                  </span>
                ) : blockingTotal > 0 ? (
                  <span className="font-medium text-emerald-600">
                    Bloqueantes resueltas
                  </span>
                ) : (
                  "Sin preguntas bloqueantes"
                )}
                {" · "}
                {answered} respondidas
              </span>
            }
            actions={
              <FilterToggle onlyBlocking={onlyBlocking} onChange={setOnlyBlocking} />
            }
          >
            {questions.length > 0 ? (
              <div className="space-y-2">
                {questions.map((q) => (
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
                    <div className="print:hidden">
                      <ScrumValidationControls
                        jobId={job.job_id}
                        targetId={q.id}
                        status={statusOf(q.id)}
                        respuesta={respuestaOf(q.id)}
                        onChanged={() => void handlePoAnswered(q.id)}
                      />
                    </div>
                    <PrintValidationState
                      status={statusOf(q.id)}
                      respuesta={respuestaOf(q.id)}
                    />
                  </div>
                ))}
              </div>
            ) : (
              <EmptyHint warn={false}>
                {onlyBlocking ? "Sin preguntas bloqueantes." : "Sin preguntas al PO."}
              </EmptyHint>
            )}
          </ArtifactSection>

          {/* 6. Análisis */}
          <ArtifactSection
            id="sec-analysis"
            index="6"
            title="Análisis"
            count={a.analysis.risks.length + a.analysis.observations.length}
            open={disc.isOpen("sec-analysis")}
            onToggle={() => disc.toggle("sec-analysis")}
            forceRender={printMode}
            preview={
              <span>
                Cobertura RF {Math.round(cov.coverage_ratio * 100)}% ·{" "}
                {a.analysis.risks.length} riesgos ·{" "}
                {a.analysis.observations.length} observaciones
              </span>
            }
          >
            <div className="space-y-4">
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

              <div>
                <GroupLabel count={a.analysis.risks.length}>Riesgos</GroupLabel>
                {a.analysis.risks.length > 0 ? (
                  <DataList>
                    {a.analysis.risks.map((r) => (
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
                ) : (
                  <EmptyHint warn={false}>Sin riesgos.</EmptyHint>
                )}
              </div>

              <div>
                <GroupLabel count={a.analysis.observations.length}>
                  Observaciones
                </GroupLabel>
                {a.analysis.observations.length > 0 ? (
                  <DataList>
                    {a.analysis.observations.map((o) => (
                      <DataRow key={o.id} id={o.id} right={<IdTag id={o.id} />}>
                        {o.description}
                        {o.reason ? (
                          <span className="text-muted-foreground"> — {o.reason}</span>
                        ) : null}
                      </DataRow>
                    ))}
                  </DataList>
                ) : (
                  <EmptyHint warn={false}>Sin observaciones.</EmptyHint>
                )}
              </div>
            </div>
          </ArtifactSection>
        </div>
      </div>

      {/* Contador flotante de bloqueantes → abre el modo enfocado */}
      {blockingRemaining > 0 && (
        <button
          type="button"
          onClick={() => setSheetOpen(true)}
          className="fixed bottom-6 left-1/2 z-30 -translate-x-1/2 rounded-full border bg-background/95 px-4 py-1.5 text-xs shadow-lg backdrop-blur transition-colors hover:border-primary/40 hover:text-primary print:hidden"
        >
          <span className="font-semibold text-red-600">{blockingRemaining}</span>{" "}
          bloqueante{blockingRemaining !== 1 ? "s" : ""} restante
          {blockingRemaining !== 1 ? "s" : ""} · responder
        </button>
      )}

      <QuestionSheet
        open={sheetOpen}
        onOpenChange={setSheetOpen}
        title="Responder preguntas al PO"
        questions={a.questions_for_po.map(
          (q): SheetQuestion => ({
            id: q.id,
            question: q.question,
            reason: q.reason,
            blocking: q.blocking,
            audience: q.audience,
            linked_to_ref: q.linked_to_ref,
          }),
        )}
        statusOf={statusOf}
        renderControls={(q, onAnswered) => (
          <ScrumValidationControls
            jobId={job.job_id}
            targetId={q.id}
            status={statusOf(q.id)}
            respuesta={respuestaOf(q.id)}
            onChanged={() => {
              void reloadSummary();
              onAnswered();
            }}
          />
        )}
      />

      <BackToTop />
    </div>
  );
}

// --- subcomponentes ----------------------------------------------------------

function FilterToggle({
  onlyBlocking,
  onChange,
}: {
  onlyBlocking: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <div className="flex rounded-lg border bg-muted/40 p-0.5 text-xs">
      <button
        type="button"
        onClick={() => onChange(false)}
        className={cn(
          "rounded-md px-2 py-0.5 transition-colors",
          !onlyBlocking
            ? "bg-background font-medium text-foreground shadow-sm"
            : "text-muted-foreground",
        )}
      >
        Todas
      </button>
      <button
        type="button"
        onClick={() => onChange(true)}
        className={cn(
          "rounded-md px-2 py-0.5 transition-colors",
          onlyBlocking
            ? "bg-background font-medium text-foreground shadow-sm"
            : "text-muted-foreground",
        )}
      >
        Bloqueantes
      </button>
    </div>
  );
}
