"use client";

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
import {
  ArtifactIndex,
  type IndexSection,
} from "@/components/artifact/artifact-index";
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
import { cn } from "@/lib/utils";

// --- utilidades --------------------------------------------------------------

function jumpTo(ref?: string | null) {
  if (!ref) return;
  const el = document.getElementById(`ref-${ref}`);
  if (!el) {
    toast.info(`Referencia ${ref} no visible en esta vista.`);
    return;
  }
  el.scrollIntoView({ behavior: "smooth", block: "center" });
  el.classList.add("ref-highlight");
  window.setTimeout(() => el.classList.remove("ref-highlight"), 1600);
}

function RefLink({ refId }: { refId?: string | null }) {
  if (!refId) return null;
  return (
    <button
      type="button"
      onClick={() => jumpTo(refId)}
      className="font-mono text-xs text-blue-600 underline underline-offset-2 hover:text-blue-800"
    >
      {refId}
    </button>
  );
}

function Count({ n }: { n: number }) {
  if (n === 0) return <span className="text-amber-600">0 ⚠</span>;
  return <span className="text-foreground">{n}</span>;
}

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
    <Badge variant="outline" className="font-mono">
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
    <div className="flex flex-col h-full">
      {/* Barra superior de afinamiento + semáforo */}
      <div className="sticky top-0 z-10 border-b bg-background/95 backdrop-blur px-6 py-3">
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <span className="font-heading font-semibold">Plan Scrum v1.0.0</span>
          <Badge variant="outline">
            {job.parent_job_id ? "v2 · afinamiento" : "v1 · original"}
          </Badge>
          {job.parent_job_id && (
            <Link
              href={`/agents/scrum/jobs/${job.parent_job_id}`}
              className="text-xs underline underline-offset-2"
            >
              ver original (<Mono>{job.parent_job_id}</Mono>)
            </Link>
          )}
          {job.input_job_id && (
            <Link
              href={`/agents/ef/jobs/${job.input_job_id}`}
              className="text-xs underline underline-offset-2"
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

          <div className="ml-auto flex gap-2">
            <Button variant="outline" size="sm" onClick={() => doExport("csv")}>
              Export ClickUp CSV
            </Button>
            <Button variant="outline" size="sm" onClick={() => doExport("json")}>
              Export JSON
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() =>
                download(
                  JSON.stringify(a, null, 2),
                  `scrum-artifact-${job.job_id}.json`,
                  "application/json",
                )
              }
            >
              Descargar artefacto
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
          <div className="mt-2 flex flex-wrap gap-2 text-[11px]">
            <CheckPill ok={checks.no_blocking_questions} label="Sin bloqueantes PO" />
            <CheckPill ok={checks.must_should_estimated} label="Must/should estimadas" />
            <CheckPill ok={checks.coverage_met} label="Cobertura RF" />
            <CheckPill ok={checks.no_must_unassigned} label="Sin must sin asignar" />
          </div>
        )}
      </div>

      {/* Cabecera: estado y métricas */}
      <div className="border-b px-6 py-4">
        <div className="flex flex-wrap items-center gap-4 text-sm">
          <JobStatusBadge status={job.status} />
          <span className="text-muted-foreground">
            tokens <Mono>{a.metrics.tokens.total}</Mono> · costo{" "}
            <Mono>${a.metrics.cost.toFixed(4)}</Mono> · historias{" "}
            <Mono>{a.metrics.stories_total}</Mono> · puntos{" "}
            <Mono>{a.metrics.points_total}</Mono> · sprints{" "}
            <Mono>{a.metrics.sprints_total}</Mono> · cobertura{" "}
            <Mono>{Math.round(a.metrics.coverage * 100)}%</Mono>
          </span>
        </div>
      </div>

      {/* Dos columnas: índice + contenido (una columna en móvil) */}
      <div className="grid grid-cols-1 gap-6 px-4 py-5 md:grid-cols-[13rem_1fr] md:px-6">
        <div className="md:sticky md:top-28 md:self-start">
          <ArtifactIndex sections={indexSections} />
        </div>

        <div className="space-y-8 min-w-0">
          {/* Banner de éxito al resolver todas las bloqueantes del PO */}
          {blockingDone && (
            <div
              className={cn(
                "rounded-lg border p-4",
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

          {/* 1. Backlog */}
          <section id="sec-backlog" className="scroll-mt-28">
            <SectionTitle>1. Backlog de producto ({a.product_backlog.method})</SectionTitle>
            {a.product_backlog.ordered_story_ids.length > 0 ? (
              <ol className="rounded-md border divide-y [&>li:nth-child(even)]:bg-muted/20">
                {a.product_backlog.ordered_story_ids.map((sid, i) => {
                  const s = storyById.get(sid);
                  return (
                    <li key={sid} className="flex items-center gap-2 p-2 text-sm">
                      <span className="w-6 text-right text-xs text-muted-foreground">
                        {i + 1}
                      </span>
                      <RefLink refId={sid} />
                      <span className="flex-1 min-w-0 truncate">{s?.goal}</span>
                      <MoscowBadge priority={s?.priority} />
                      <PointsBadge points={s?.story_points} />
                    </li>
                  );
                })}
              </ol>
            ) : (
              <p className="text-amber-600 text-sm">0 ⚠ backlog vacío</p>
            )}
            {a.product_backlog.rationale && (
              <p className="mt-1 text-xs text-muted-foreground">
                {a.product_backlog.rationale}
              </p>
            )}
          </section>

          {/* 2. Sprints */}
          <section id="sec-sprints" className="scroll-mt-28 space-y-3">
            <SectionTitle>2. Sprints</SectionTitle>
            {a.sprints.map((sp) => (
              <div key={sp.id} className="rounded-md border p-3">
                <div className="flex flex-wrap items-center gap-2 text-sm">
                  <Mono>{sp.id}</Mono>
                  <Badge variant="outline" className="font-mono">
                    {sp.total_points}/{sp.capacity_points} pts
                  </Badge>
                  <span className="text-muted-foreground">{sp.goal}</span>
                </div>
                <ul className="mt-2 flex flex-wrap gap-2">
                  {sp.story_ids.map((sid) => (
                    <li key={sid}>
                      <RefLink refId={sid} />
                    </li>
                  ))}
                </ul>
              </div>
            ))}
            {a.unassigned_story_ids.length > 0 ? (
              <div className="rounded-md border border-amber-300 bg-amber-50/50 p-3">
                <div className="text-sm text-amber-800">
                  ⚠ Sin asignar (<Count n={a.unassigned_story_ids.length} />)
                </div>
                <ul className="mt-1 flex flex-wrap gap-2">
                  {a.unassigned_story_ids.map((sid) => (
                    <li key={sid}>
                      <RefLink refId={sid} />
                    </li>
                  ))}
                </ul>
              </div>
            ) : (
              <p className="text-xs text-muted-foreground">
                Todas las historias estimadas quedaron asignadas.
              </p>
            )}
          </section>

          {/* 3. Historias */}
          <section id="sec-stories" className="scroll-mt-28 space-y-3">
            <SectionTitle>3. Historias de usuario</SectionTitle>
            {a.stories.map((s) => (
              <div key={s.id} id={`ref-${s.id}`} className="rounded-md border p-3">
                <div className="flex flex-wrap items-center gap-2 text-sm">
                  <Mono>{s.id}</Mono>
                  <MoscowBadge priority={s.priority} />
                  <PointsBadge points={s.story_points} />
                  {s.epic_ref && (
                    <span className="text-xs text-muted-foreground">
                      épica <RefLink refId={s.epic_ref} />
                    </span>
                  )}
                  <ConfidenceBadge value={s.confidence} />
                </div>
                <p className="mt-1 text-sm font-medium">{s.statement}</p>

                {/* Trazabilidad al EF */}
                <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
                  <span>
                    RF:{" "}
                    {s.source_refs.requirement_refs.map((r) => (
                      <span key={r} className="ml-1">
                        <RefLink refId={r} />
                      </span>
                    ))}
                  </span>
                  {s.source_refs.rule_refs.length > 0 && (
                    <span>
                      reglas:{" "}
                      {s.source_refs.rule_refs.map((r) => (
                        <span key={r} className="ml-1">
                          <RefLink refId={r} />
                        </span>
                      ))}
                    </span>
                  )}
                  {s.dependencies.length > 0 && (
                    <span>
                      depende de:{" "}
                      {s.dependencies.map((r) => (
                        <span key={r} className="ml-1">
                          <RefLink refId={r} />
                        </span>
                      ))}
                    </span>
                  )}
                </div>

                {/* Criterios de aceptación (Gherkin) */}
                {s.acceptance_criteria.length > 0 ? (
                  <div className="mt-2 space-y-1">
                    {s.acceptance_criteria.map((c) => (
                      <div key={c.id} className="rounded bg-muted/40 p-2 text-xs">
                        <Mono>{c.id}</Mono>{" "}
                        {c.format === "gherkin" ? (
                          <span>
                            <b>Dado</b> {c.given} <b>cuando</b> {c.when}{" "}
                            <b>entonces</b> {c.then}
                          </span>
                        ) : (
                          <span>{c.text}</span>
                        )}{" "}
                        {c.source_refs.map((r) => (
                          <span key={r} className="ml-1">
                            <RefLink refId={r} />
                          </span>
                        ))}
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="mt-2 text-xs text-amber-600">
                    0 ⚠ sin criterios de aceptación
                  </p>
                )}

                {/* Estimación sugerida */}
                {s.estimation_rationale && (
                  <p className="mt-1 text-xs text-muted-foreground">
                    Estimación sugerida: {s.estimation_rationale}{" "}
                    <ConfidenceBadge value={s.estimation_confidence} />
                  </p>
                )}
              </div>
            ))}
          </section>

          {/* 4. Épicas */}
          <section id="sec-epics" className="scroll-mt-28 space-y-2">
            <SectionTitle>4. Épicas</SectionTitle>
            {a.epics.map((e) => (
              <div key={e.id} id={`ref-${e.id}`} className="rounded-md border p-3">
                <div className="flex items-center gap-2 text-sm">
                  <Mono>{e.id}</Mono>
                  <span className="font-medium">{e.title}</span>
                  <ConfidenceBadge value={e.confidence} />
                </div>
                {e.description && (
                  <p className="text-xs text-muted-foreground">{e.description}</p>
                )}
                <div className="mt-1 text-xs text-muted-foreground">
                  origen:{" "}
                  {e.source_refs.map((r) => (
                    <span key={r} className="ml-1">
                      <RefLink refId={r} />
                    </span>
                  ))}{" "}
                  · historias:{" "}
                  {e.story_ids.map((r) => (
                    <span key={r} className="ml-1">
                      <RefLink refId={r} />
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </section>

          {/* 5. Preguntas al PO */}
          <section id="sec-questions" className="scroll-mt-28">
            <div className="flex items-center justify-between">
              <SectionTitle>5. Preguntas al Product Owner</SectionTitle>
              <div className="flex gap-1 text-xs">
                <button
                  type="button"
                  onClick={() => setOnlyBlocking(false)}
                  className={cn(
                    "rounded px-2 py-0.5",
                    !onlyBlocking ? "bg-accent font-medium" : "text-muted-foreground",
                  )}
                >
                  Todas
                </button>
                <button
                  type="button"
                  onClick={() => setOnlyBlocking(true)}
                  className={cn(
                    "rounded px-2 py-0.5",
                    onlyBlocking ? "bg-accent font-medium" : "text-muted-foreground",
                  )}
                >
                  Bloqueantes
                </button>
              </div>
            </div>
            {questions.length > 0 ? (
              <div className="space-y-2">
                {questions.map((q) => (
                  <div
                    key={q.id}
                    id={`ref-${q.id}`}
                    className={cn(
                      "rounded-md border p-3",
                      q.blocking && "border-red-300 bg-red-50/40",
                    )}
                  >
                    <div className="flex flex-wrap items-center gap-2 text-sm">
                      <Mono>{q.id}</Mono>
                      <AudienceBadge audience={q.audience} />
                      {q.blocking && <Badge className="bg-red-600">bloqueante</Badge>}
                      {q.linked_to_ref && (
                        <span className="text-xs text-muted-foreground">
                          ligada a <RefLink refId={q.linked_to_ref} />
                        </span>
                      )}
                    </div>
                    <p className="mt-1 text-sm font-medium">{q.question}</p>
                    <p className="text-xs text-muted-foreground">Motivo: {q.reason}</p>
                    <ScrumValidationControls
                      jobId={job.job_id}
                      targetId={q.id}
                      status={statusOf(q.id)}
                      respuesta={respuestaOf(q.id)}
                      onChanged={() => void handlePoAnswered(q.id)}
                    />
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-muted-foreground text-sm">
                {onlyBlocking ? "Sin preguntas bloqueantes." : "Sin preguntas al PO."}
              </p>
            )}
          </section>

          {/* 6. Análisis */}
          <section id="sec-analysis" className="scroll-mt-28 space-y-4">
            <SectionTitle>6. Análisis</SectionTitle>

            <div className="rounded-md border p-3 text-sm">
              <div className="text-xs font-semibold text-muted-foreground mb-1">
                Cobertura de requisitos funcionales
              </div>
              <p>
                {cov.requirements_covered} / {cov.requirements_total} cubiertos (
                {Math.round(cov.coverage_ratio * 100)}%)
              </p>
              {cov.uncovered_requirement_refs.length > 0 ? (
                <p className="mt-1 text-amber-700">
                  ⚠ No cubiertos:{" "}
                  {cov.uncovered_requirement_refs.map((r) => (
                    <span key={r} className="ml-1">
                      <RefLink refId={r} />
                    </span>
                  ))}
                </p>
              ) : (
                <p className="mt-1 text-emerald-700 text-xs">
                  Todos los RF quedaron cubiertos.
                </p>
              )}
            </div>

            <div>
              <div className="text-xs font-semibold text-muted-foreground mb-1">
                Riesgos <Count n={a.analysis.risks.length} />
              </div>
              {a.analysis.risks.length > 0 && (
                <div className="rounded-md border divide-y">
                  {a.analysis.risks.map((r) => (
                    <div key={r.id} className="p-2 text-sm">
                      <Mono>{r.id}</Mono>{" "}
                      <Badge variant="outline" className="ml-1">
                        {r.severity}
                      </Badge>{" "}
                      {r.description}
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div>
              <div className="text-xs font-semibold text-muted-foreground mb-1">
                Observaciones <Count n={a.analysis.observations.length} />
              </div>
              {a.analysis.observations.length > 0 && (
                <div className="rounded-md border divide-y">
                  {a.analysis.observations.map((o) => (
                    <div key={o.id} className="p-2 text-sm">
                      <Mono>{o.id}</Mono> {o.description}
                      {o.reason ? (
                        <span className="text-xs text-muted-foreground"> — {o.reason}</span>
                      ) : null}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </section>
        </div>
      </div>

      {/* Contador flotante de bloqueantes restantes */}
      {blockingRemaining > 0 && (
        <div className="fixed bottom-6 left-1/2 z-30 -translate-x-1/2 rounded-full border bg-background/95 px-4 py-1.5 text-xs shadow-lg backdrop-blur">
          <span className="font-semibold text-red-600">{blockingRemaining}</span>{" "}
          bloqueante{blockingRemaining !== 1 ? "s" : ""} restante
          {blockingRemaining !== 1 ? "s" : ""}
        </div>
      )}

      <BackToTop />
    </div>
  );
}

// --- subcomponentes ----------------------------------------------------------

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="mb-2 text-sm font-heading font-semibold uppercase tracking-wide text-muted-foreground">
      {children}
    </h2>
  );
}

function CheckPill({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5",
        ok
          ? "border-emerald-300 bg-emerald-50 text-emerald-700"
          : "border-slate-300 bg-slate-50 text-slate-500",
      )}
    >
      {ok ? "✓" : "○"} {label}
    </span>
  );
}
