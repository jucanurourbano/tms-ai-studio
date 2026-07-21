"use client";

import { Kanban } from "lucide-react";
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
import {
  ArtifactIndex,
  type IndexSection,
} from "@/components/artifact/artifact-index";
import { ArtifactSkeleton } from "@/components/artifact/artifact-skeleton";
import { BackToTop } from "@/components/artifact/back-to-top";
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
import type {
  EFArtifact,
  JobDetail,
  QuestionStatus,
  ValidationSummary,
} from "@/lib/types/ef";
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

/** Conteo con estado vacío EXPLÍCITO (nunca oculto). */
function Count({ n }: { n: number }) {
  if (n === 0) {
    return <span className="text-amber-600">0 ⚠</span>;
  }
  return <span className="text-foreground">{n}</span>;
}

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

  const scrollToRef = useCallback((id: string) => {
    const el = document.getElementById(`ref-${id}`);
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    el.classList.add("ref-highlight");
    window.setTimeout(() => el.classList.remove("ref-highlight"), 1600);
  }, []);

  // Al responder una pregunta bloqueante, salta a la siguiente pendiente.
  const handleQuestionAnswered = useCallback(
    async (answeredId: string) => {
      const s = await reloadSummary();
      if (!s || !artifact) return;
      const statusIn = (id: string) =>
        s.validations.find((v) => v.target_id === id)?.status ?? "pendiente";
      const next = artifact.questions_for_analyst.find(
        (q) => q.blocking && q.id !== answeredId && statusIn(q.id) === "pendiente",
      );
      if (next) scrollToRef(next.id);
    },
    [reloadSummary, artifact, scrollToRef],
  );

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
  const questions = onlyBlocking
    ? a.questions_for_analyst.filter((q) => q.blocking)
    : a.questions_for_analyst;
  const analysis = a.analysis ?? {};
  const modelCounts: [string, number, string][] = [
    ["Actores", a.actors.length, "m-actors"],
    ["Módulos", a.modules.length, "m-modules"],
    ["Menús", a.menus.length, "m-menus"],
    ["Procesos", a.processes.length, "m-processes"],
    ["Reglas", a.business_rules.length, "m-rules"],
    ["Validaciones", a.validations.length, "m-validations"],
    ["Campos", a.fields.length, "m-fields"],
    ["Entidades", a.entities.length, "m-entities"],
    ["Relaciones", a.relationships.length, "m-relationships"],
    ["CRUD", a.crud.length, "m-crud"],
    ["APIs", a.apis.length, "m-apis"],
  ];
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
  const blockingTotal = a.questions_for_analyst.filter((q) => q.blocking).length;
  const blockingRemaining = a.questions_for_analyst.filter(
    (q) => q.blocking && statusOf(q.id) === "pendiente",
  ).length;
  const blockingDone = blockingTotal > 0 && blockingRemaining === 0;

  const indexSections: IndexSection[] = [
    { id: "sec-interpretation", label: "Interpretación" },
    {
      id: "sec-questions",
      label: "Preguntas",
      count: a.questions_for_analyst.length,
      meta: `${blockingTotal} bloq.`,
    },
    { id: "sec-requirements", label: "Requisitos", count: reqTotal },
    {
      id: "sec-model",
      label: "Modelo",
      children: modelCounts.map(([label, n, id]) => ({ id, label, count: n })),
    },
    { id: "sec-analysis", label: "Análisis crítico", count: analysisTotal },
  ];

  return (
    <div className="flex flex-col h-full">
      {/* Barra superior de afinamiento */}
      <div className="sticky top-0 z-10 border-b bg-background/95 backdrop-blur px-6 py-3">
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <span className="font-heading font-semibold">EF v1.2.0</span>
          <Badge variant="outline">
            {job.parent_job_id ? "v2 · afinamiento" : "v1 · original"}
          </Badge>
          {job.parent_job_id && (
            <Link
              href={`/agents/ef/jobs/${job.parent_job_id}`}
              className="text-xs underline underline-offset-2"
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

          <div className="ml-auto flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() =>
                void navigator.clipboard
                  .writeText(buildProcesosText(a, statusOf))
                  .then(() => toast.success("Copiado para Procesos"))
              }
            >
              Copiar para Procesos
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => downloadJson(a, job.job_id)}
            >
              Descargar JSON
            </Button>
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
                  <Button
                    onClick={doRefine}
                    disabled={refining || !canRefine}
                  >
                    {refining ? "Regenerando…" : "Confirmar y regenerar"}
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </div>
        </div>
      </div>

      {/* Cabecera: estado, fuente y métricas */}
      <div className="border-b px-6 py-4">
        <div className="flex flex-wrap items-center gap-4 text-sm">
          <JobStatusBadge status={job.status} />
          <span className="text-muted-foreground">
            Fuente: {a.source.type} · {a.source.fidelity}
            {a.source.filename ? ` · ${a.source.filename}` : ""}
          </span>
          <span className="text-muted-foreground">
            tokens <Mono>{a.metrics.tokens.total}</Mono> · costo{" "}
            <Mono>${a.metrics.cost.toFixed(4)}</Mono> · duración{" "}
            <Mono>{a.metrics.duration}s</Mono> · cobertura{" "}
            <Mono>{Math.round(a.metrics.coverage * 100)}%</Mono>
          </span>
        </div>
        <p className="mt-1 text-sm">{a.summary}</p>
      </div>

      {/* Dos columnas: índice + contenido (una columna en móvil) */}
      <div className="grid grid-cols-1 gap-6 px-4 py-5 md:grid-cols-[13rem_1fr] md:px-6">
        {/* Índice navegable (scrollspy + sub-grupo plegable); select en móvil */}
        <div className="md:sticky md:top-24 md:self-start">
          <ArtifactIndex sections={indexSections} />
        </div>

        {/* Contenido */}
        <div className="space-y-8 min-w-0">
          {/* Banner de éxito al resolver todas las bloqueantes */}
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
                    className={buttonVariants({
                      size: "sm",
                      className: "gap-1.5",
                    })}
                  >
                    <Kanban className="h-3.5 w-3.5" />
                    Generar plan Scrum
                  </Link>
                )}
              </div>
            </div>
          )}

          {/* 1. Interpretación para Sistemas */}
          <section id="sec-interpretation" className="scroll-mt-24">
            <SectionTitle>1. Interpretación para Sistemas</SectionTitle>
            <div className="rounded-md border p-3 text-sm space-y-3">
              <div>
                <div className="text-xs font-semibold text-muted-foreground">
                  Qué pide Procesos
                </div>
                <p>{si.what_process_requests}</p>
              </div>

              <div>
                <div className="text-xs font-semibold text-muted-foreground">
                  Alcance para Sistemas
                </div>
                {si.scope_for_systems && si.scope_for_systems.length > 0 ? (
                  <ul className="space-y-1">
                    {si.scope_for_systems.map((s, i) => (
                      <li key={s.id ?? i} className="text-sm">
                        {s.description}{" "}
                        {s.requirement_refs?.map((r) => (
                          <span key={r} className="ml-1">
                            <RefLink refId={r} />
                          </span>
                        ))}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-amber-600 text-sm">0 ⚠ sin alcance definido</p>
                )}
              </div>

              <div>
                <div className="text-xs font-semibold text-muted-foreground">
                  Aparentemente fuera de alcance
                </div>
                {si.apparent_out_of_scope &&
                si.apparent_out_of_scope.length > 0 ? (
                  <ul className="list-disc pl-5 text-sm">
                    {si.apparent_out_of_scope.map((s, i) => (
                      <li key={s.id ?? i}>
                        {s.description}
                        {s.reason ? (
                          <span className="text-muted-foreground">
                            {" "}
                            — {s.reason}
                          </span>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-muted-foreground text-sm">
                    0 · nada marcado fuera de alcance
                  </p>
                )}
              </div>

              <div>
                <div className="text-xs font-semibold text-muted-foreground">
                  Supuestos de interpretación (validables)
                </div>
                {assumptions.length > 0 ? (
                  <div className="space-y-2">
                    {assumptions.map((s) => (
                      <div
                        key={s.id}
                        id={`ref-${s.id}`}
                        className="rounded-md border p-2"
                      >
                        <div className="flex items-center gap-2 text-sm">
                          <Mono>{s.id}</Mono>
                          <OriginBadge origin={s.origin} />
                          <ConfidenceBadge value={s.confidence} />
                        </div>
                        <p className="text-sm">{s.assumption}</p>
                        {s.rationale && (
                          <p className="text-xs text-muted-foreground">
                            {s.rationale}
                          </p>
                        )}
                        <ValidationControls
                          jobId={job.job_id}
                          targetType="assumption"
                          targetId={s.id}
                          status={statusOf(s.id)}
                          respuesta={respuestaOf(s.id)}
                          onChanged={reloadSummary}
                        />
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-amber-600 text-sm">0 ⚠ sin supuestos</p>
                )}
              </div>
            </div>
          </section>

          {/* 2. Preguntas al analista */}
          <section id="sec-questions" className="scroll-mt-24">
            <div className="flex items-center justify-between">
              <SectionTitle>2. Preguntas al analista</SectionTitle>
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
                      {q.blocking && (
                        <Badge className="bg-red-600">bloqueante</Badge>
                      )}
                      {q.linked_to_ref && (
                        <span className="text-xs text-muted-foreground">
                          ligada a <RefLink refId={q.linked_to_ref} />
                        </span>
                      )}
                    </div>
                    <p className="mt-1 text-sm font-medium">{q.question}</p>
                    <p className="text-xs text-muted-foreground">
                      Motivo: {q.reason}
                    </p>
                    <ValidationControls
                      jobId={job.job_id}
                      targetType="question"
                      targetId={q.id}
                      status={statusOf(q.id)}
                      respuesta={respuestaOf(q.id)}
                      onChanged={() => void handleQuestionAnswered(q.id)}
                    />
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-amber-600 text-sm">
                {onlyBlocking ? "Sin preguntas bloqueantes." : "0 ⚠ sin preguntas"}
              </p>
            )}
          </section>

          {/* 3. Requisitos */}
          <section id="sec-requirements" className="scroll-mt-24">
            <SectionTitle>3. Requisitos</SectionTitle>
            {(
              [
                ["Negocio", a.requirements.business],
                ["Funcionales", a.requirements.functional],
                ["No funcionales", a.requirements.non_functional],
              ] as const
            ).map(([label, list]) => (
              <div key={label} className="mb-4">
                <div className="text-xs font-semibold text-muted-foreground mb-1">
                  {label} <Count n={list.length} />
                </div>
                {list.length > 0 ? (
                  <div className="rounded-md border divide-y [&>div:nth-child(even)]:bg-muted/20">
                    {list.map((r) => (
                      <div
                        key={r.id}
                        id={`ref-${r.id}`}
                        className="p-2 hover:bg-muted/40"
                      >
                        <button
                          type="button"
                          onClick={() => toggle(r.id)}
                          className="flex w-full items-center gap-2 text-left text-sm"
                        >
                          <Mono>{r.id}</Mono>
                          <span className="flex-1">{r.text}</span>
                          <OriginBadge origin={r.origin} />
                          <ConfidenceBadge value={r.confidence} />
                        </button>
                        {expanded.has(r.id) && (
                          <div className="mt-2 pl-2 text-xs space-y-1">
                            <div>
                              source_ref:{" "}
                              <Mono>{r.source_ref ?? "—"}</Mono>
                            </div>
                            <div className="text-muted-foreground">evidence:</div>
                            <pre className="whitespace-pre-wrap rounded bg-muted p-2 font-mono text-[11px]">
                              {r.evidence ?? "— sin evidencia —"}
                            </pre>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
            ))}
          </section>

          {/* 4. Modelo */}
          <section id="sec-model" className="scroll-mt-24 space-y-4">
            <SectionTitle>4. Modelo</SectionTitle>
            <ModelBlock id="m-actors" title="Actores" n={a.actors.length}>
              {a.actors.map((x) => (
                <ItemRow key={x.id} id={x.id} origin={x.origin}>
                  {x.name}
                </ItemRow>
              ))}
            </ModelBlock>
            <ModelBlock id="m-modules" title="Módulos" n={a.modules.length}>
              {a.modules.map((x) => (
                <ItemRow key={x.id} id={x.id} origin={x.origin}>
                  {x.name}
                </ItemRow>
              ))}
            </ModelBlock>
            <ModelBlock id="m-menus" title="Menús" n={a.menus.length}>
              {a.menus.map((x) => (
                <ItemRow key={x.id} id={x.id} origin={x.origin}>
                  {x.name} {x.path ? <Mono>{x.path}</Mono> : null}
                </ItemRow>
              ))}
            </ModelBlock>
            <ModelBlock id="m-processes" title="Procesos" n={a.processes.length}>
              {a.processes.map((x) => (
                <ItemRow key={x.id} id={x.id} origin={x.origin}>
                  {x.name}
                  {x.steps && x.steps.length > 0 ? (
                    <span className="text-xs text-muted-foreground">
                      {" "}
                      · {x.steps.join(" → ")}
                    </span>
                  ) : null}
                </ItemRow>
              ))}
            </ModelBlock>
            <ModelBlock id="m-rules" title="Reglas" n={a.business_rules.length}>
              {a.business_rules.map((x) => (
                <ItemRow key={x.id} id={x.id} origin={x.origin}>
                  {x.statement}
                </ItemRow>
              ))}
            </ModelBlock>
            <ModelBlock
              id="m-validations"
              title="Validaciones"
              n={a.validations.length}
            >
              {a.validations.map((x) => (
                <ItemRow key={x.id} id={x.id} origin={x.origin}>
                  {x.rule}{" "}
                  {x.field_ref ? (
                    <span className="text-xs">
                      (<RefLink refId={x.field_ref} />)
                    </span>
                  ) : null}
                </ItemRow>
              ))}
            </ModelBlock>
            <ModelBlock id="m-fields" title="Campos" n={a.fields.length}>
              {a.fields.map((x) => (
                <ItemRow key={x.id} id={x.id} origin={x.origin}>
                  <Mono>{x.name}</Mono>
                  <span className="text-xs text-muted-foreground">
                    {" "}
                    {x.data_type ?? "?"} {x.required ? "· requerido" : ""}
                    {x.entity_ref ? " · " : ""}
                  </span>
                  {x.entity_ref ? <RefLink refId={x.entity_ref} /> : null}
                </ItemRow>
              ))}
            </ModelBlock>
            <ModelBlock id="m-entities" title="Entidades" n={a.entities.length}>
              {a.entities.map((x) => (
                <ItemRow key={x.id} id={x.id} origin={x.origin}>
                  {x.name}
                </ItemRow>
              ))}
            </ModelBlock>
            <ModelBlock
              id="m-relationships"
              title="Relaciones"
              n={a.relationships.length}
            >
              {a.relationships.map((x) => (
                <ItemRow key={x.id} id={x.id} origin={x.origin}>
                  <RefLink refId={x.source_entity_ref} />{" "}
                  <Mono>{x.cardinality}</Mono>{" "}
                  <RefLink refId={x.target_entity_ref} />
                </ItemRow>
              ))}
            </ModelBlock>
            <ModelBlock id="m-crud" title="CRUD" n={a.crud.length}>
              {a.crud.map((x) => (
                <ItemRow key={x.id} id={x.id} origin={x.origin}>
                  <RefLink refId={x.entity_ref} />
                  <span className="ml-2 font-mono text-xs">
                    {x.create ? "C" : "-"}
                    {x.read ? "R" : "-"}
                    {x.update ? "U" : "-"}
                    {x.delete ? "D" : "-"}
                  </span>
                </ItemRow>
              ))}
            </ModelBlock>
            <ModelBlock id="m-apis" title="APIs" n={a.apis.length}>
              {a.apis.map((x) => (
                <ItemRow key={x.id} id={x.id} origin={x.origin}>
                  <Mono>
                    {x.method} {x.path}
                  </Mono>
                </ItemRow>
              ))}
            </ModelBlock>
          </section>

          {/* 5. Análisis crítico */}
          <section id="sec-analysis" className="scroll-mt-24 space-y-4">
            <SectionTitle>5. Análisis crítico</SectionTitle>
            <ModelBlock title="Ambigüedades" n={analysis.ambiguities?.length ?? 0}>
              {(analysis.ambiguities ?? []).map((x) => (
                <ItemRow key={x.id} id={x.id}>
                  {x.description}
                </ItemRow>
              ))}
            </ModelBlock>
            <ModelBlock title="Faltantes" n={analysis.missing_info?.length ?? 0}>
              {(analysis.missing_info ?? []).map((x) => (
                <ItemRow key={x.id} id={x.id}>
                  {x.description}
                  {x.expected_where ? (
                    <span className="text-xs text-muted-foreground">
                      {" "}
                      — esperado en: {x.expected_where}
                    </span>
                  ) : null}
                </ItemRow>
              ))}
            </ModelBlock>
            <ModelBlock
              title="Inconsistencias"
              n={analysis.inconsistencies?.length ?? 0}
            >
              {(analysis.inconsistencies ?? []).map((x) => (
                <ItemRow key={x.id} id={x.id}>
                  {x.description}
                  {x.conflicting_refs && x.conflicting_refs.length > 0 ? (
                    <span className="ml-1">
                      {x.conflicting_refs.map((r) => (
                        <span key={r} className="ml-1">
                          <RefLink refId={r} />
                        </span>
                      ))}
                    </span>
                  ) : null}
                </ItemRow>
              ))}
            </ModelBlock>
            <ModelBlock
              title="Observaciones"
              n={analysis.observations?.length ?? 0}
            >
              {(analysis.observations ?? []).map((x) => (
                <ItemRow key={x.id} id={x.id}>
                  {x.description}
                  {x.reason ? (
                    <span className="text-xs text-muted-foreground">
                      {" "}
                      — {x.reason}
                    </span>
                  ) : null}
                </ItemRow>
              ))}
            </ModelBlock>
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

function ModelBlock({
  id,
  title,
  n,
  children,
}: {
  id?: string;
  title: string;
  n: number;
  children: React.ReactNode;
}) {
  return (
    <div id={id} className="scroll-mt-24">
      <div className="text-xs font-semibold text-muted-foreground mb-1">
        {title} <Count n={n} />
      </div>
      {n > 0 ? (
        <div className="rounded-md border divide-y [&>div:nth-child(even)]:bg-muted/20">
          {children}
        </div>
      ) : (
        <p className="text-amber-600 text-xs">0 ⚠ vacío</p>
      )}
    </div>
  );
}

function ItemRow({
  id,
  origin,
  children,
}: {
  id: string;
  origin?: "stated" | "derived" | null;
  children: React.ReactNode;
}) {
  return (
    <div
      id={`ref-${id}`}
      className="flex items-center gap-2 p-2 text-sm hover:bg-muted/40"
    >
      <Mono>{id}</Mono>
      <span className="flex-1 min-w-0">{children}</span>
      {origin === "derived" ? <OriginBadge origin={origin} /> : null}
    </div>
  );
}
