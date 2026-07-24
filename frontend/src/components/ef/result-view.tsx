"use client";

import {
  ClipboardCopy,
  Clock,
  Coins,
  Download,
  DollarSign,
  Kanban,
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
} from "@/components/artifact/primitives";
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
import { useDisclosure } from "@/lib/use-disclosure";
import { usePersistentState } from "@/lib/use-persistent-state";
import { usePrintExpand } from "@/lib/use-print-expand";
import { cn } from "@/lib/utils";

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
  const [sheetOpen, setSheetOpen] = useState(false);
  const [indexCollapsed, setIndexCollapsed] = usePersistentState(
    "artifact:index-collapsed",
    false,
  );
  const disc = useDisclosure(2);
  const { printMode, printNow } = usePrintExpand();

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
  const modelTotal = modelCounts.reduce((acc, [, n]) => acc + n, 0);
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
    <div className="flex h-full flex-col">
      <PrintCover
        kind="Análisis de Especificación Funcional"
        title={a.source.filename || "Análisis EF"}
        subtitle={a.summary}
        version="1.2.0"
        stats={[
          { label: "requisitos", value: String(reqTotal) },
          { label: "preguntas", value: String(a.questions_for_analyst.length) },
          { label: "cobertura", value: `${Math.round(a.metrics.coverage * 100)}%` },
          { label: "costo", value: `$${a.metrics.cost.toFixed(4)}` },
        ]}
      />
      <PrintToc
        items={[
          "Interpretación para Sistemas",
          "Preguntas al analista",
          "Requisitos",
          "Modelo",
          "Análisis crítico",
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

          <div className="ml-auto flex flex-wrap gap-2">
            {a.questions_for_analyst.length > 0 && (
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
          </div>
        </div>
      </div>

      {/* Cabecera: estado, fuente y mini-stats */}
      <div className="border-b px-6 py-4">
        <div className="mb-3 flex flex-wrap items-center gap-3 text-sm">
          <JobStatusBadge status={job.status} />
          <span className="text-xs text-muted-foreground">
            Fuente: {a.source.type} · {a.source.fidelity}
            {a.source.filename ? ` · ${a.source.filename}` : ""}
          </span>
        </div>
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
          <Stat icon={<Clock />} value={`${a.metrics.duration}s`} label="duración" />
          <Stat
            icon={<Target />}
            value={`${Math.round(a.metrics.coverage * 100)}%`}
            label="cobertura"
          />
        </StatRow>
        <p className="mt-3 max-w-full text-sm text-muted-foreground">{a.summary}</p>
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
        <div className="md:sticky md:top-24 md:self-start print:hidden">
          <ArtifactIndexPanel
            sections={indexSections}
            collapsed={indexCollapsed}
            onToggle={() => setIndexCollapsed((v) => !v)}
            onNavigate={disc.openOnly}
            openIds={disc.openIds}
          />
        </div>

        {/* Contenido */}
        <div className="min-w-0 space-y-6">
          {/* Banner de éxito al resolver todas las bloqueantes */}
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

          {/* 1. Interpretación para Sistemas */}
          <ArtifactSection
            id="sec-interpretation"
            index="1"
            title="Interpretación para Sistemas"
            meta={`${si.scope_for_systems?.length ?? 0} alcance · ${assumptions.length} supuestos`}
            open={disc.isOpen("sec-interpretation")}
            onToggle={() => disc.toggle("sec-interpretation")}
            forceRender={printMode}
            preview={<span className="line-clamp-2">{si.what_process_requests}</span>}
          >
            <div className="space-y-4">
              <div>
                <GroupLabel>Qué pide Procesos</GroupLabel>
                <p className="text-sm">{si.what_process_requests}</p>
              </div>

              <div>
                <GroupLabel count={si.scope_for_systems?.length}>
                  Alcance para Sistemas
                </GroupLabel>
                {si.scope_for_systems && si.scope_for_systems.length > 0 ? (
                  <DataList>
                    {si.scope_for_systems.map((s, i) => (
                      <DataRow
                        key={s.id ?? i}
                        index={i + 1}
                        right={s.requirement_refs?.map((r) => (
                          <RefChip key={r} refId={r} />
                        ))}
                      >
                        {s.description}
                      </DataRow>
                    ))}
                  </DataList>
                ) : (
                  <EmptyHint>Sin alcance definido.</EmptyHint>
                )}
              </div>

              <div>
                <GroupLabel count={si.apparent_out_of_scope?.length}>
                  Aparentemente fuera de alcance
                </GroupLabel>
                {si.apparent_out_of_scope &&
                si.apparent_out_of_scope.length > 0 ? (
                  <DataList>
                    {si.apparent_out_of_scope.map((s, i) => (
                      <DataRow key={s.id ?? i} index={i + 1}>
                        {s.description}
                        {s.reason ? (
                          <span className="text-muted-foreground"> — {s.reason}</span>
                        ) : null}
                      </DataRow>
                    ))}
                  </DataList>
                ) : (
                  <EmptyHint warn={false}>Nada marcado fuera de alcance.</EmptyHint>
                )}
              </div>

              <div>
                <GroupLabel count={assumptions.length}>
                  Supuestos de interpretación (validables)
                </GroupLabel>
                {assumptions.length > 0 ? (
                  <div className="space-y-2">
                    {assumptions.map((s) => (
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
                ) : (
                  <EmptyHint>Sin supuestos.</EmptyHint>
                )}
              </div>
            </div>
          </ArtifactSection>

          {/* 2. Preguntas al analista */}
          <ArtifactSection
            id="sec-questions"
            index="2"
            title="Preguntas al analista"
            count={a.questions_for_analyst.length}
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
                {progress.answered} de {progress.total} respondidas
              </span>
            }
            actions={
              <FilterToggle
                onlyBlocking={onlyBlocking}
                onChange={setOnlyBlocking}
              />
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
                      {q.blocking && (
                        <Badge className="bg-red-600">bloqueante</Badge>
                      )}
                      {q.linked_to_ref && (
                        <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                          ligada a <RefChip refId={q.linked_to_ref} />
                        </span>
                      )}
                    </div>
                    <p className="mt-1.5 text-sm font-medium">{q.question}</p>
                    <p className="text-xs text-muted-foreground">
                      Motivo: {q.reason}
                    </p>
                    <div className="print:hidden">
                      <ValidationControls
                        jobId={job.job_id}
                        targetType="question"
                        targetId={q.id}
                        status={statusOf(q.id)}
                        respuesta={respuestaOf(q.id)}
                        onChanged={() => void handleQuestionAnswered(q.id)}
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
              <EmptyHint warn={!onlyBlocking}>
                {onlyBlocking ? "Sin preguntas bloqueantes." : "Sin preguntas."}
              </EmptyHint>
            )}
          </ArtifactSection>

          {/* 3. Requisitos */}
          <ArtifactSection
            id="sec-requirements"
            index="3"
            title="Requisitos"
            count={reqTotal}
            open={disc.isOpen("sec-requirements")}
            onToggle={() => disc.toggle("sec-requirements")}
            forceRender={printMode}
            preview={
              <span>
                {a.requirements.business.length} de negocio ·{" "}
                {a.requirements.functional.length} funcionales ·{" "}
                {a.requirements.non_functional.length} no funcionales
              </span>
            }
          >
            <div className="space-y-4">
              {(
                [
                  ["Negocio", a.requirements.business],
                  ["Funcionales", a.requirements.functional],
                  ["No funcionales", a.requirements.non_functional],
                ] as const
              ).map(([label, list]) => (
                <div key={label}>
                  <GroupLabel count={list.length}>{label}</GroupLabel>
                  {list.length > 0 ? (
                    <DataList>
                      {list.map((r, i) => (
                        <div key={r.id} id={`ref-${r.id}`} className="print-atom">
                          <button
                            type="button"
                            onClick={() => toggle(r.id)}
                            className="flex w-full items-start gap-3 px-3 py-2 text-left transition-colors hover:bg-primary/[0.04]"
                          >
                            <span className="w-5 shrink-0 pt-0.5 text-right font-mono text-[11px] tabular-nums text-muted-foreground/70">
                              {i + 1}
                            </span>
                            <span className="min-w-0 flex-1 text-sm">{r.text}</span>
                            <span className="flex shrink-0 items-center gap-1.5 pt-0.5">
                              <OriginBadge origin={r.origin} />
                              <ConfidenceBadge value={r.confidence} />
                              <IdTag id={r.id} />
                            </span>
                          </button>
                          {expanded.has(r.id) && (
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
                      ))}
                    </DataList>
                  ) : (
                    <EmptyHint>Sin requisitos de {label.toLowerCase()}.</EmptyHint>
                  )}
                </div>
              ))}
            </div>
          </ArtifactSection>

          {/* 4. Modelo */}
          <ArtifactSection
            id="sec-model"
            index="4"
            title="Modelo"
            count={modelTotal}
            open={disc.isOpen("sec-model")}
            onToggle={() => disc.toggle("sec-model")}
            forceRender={printMode}
            preview={
              <span>
                {a.entities.length} entidades · {a.processes.length} procesos ·{" "}
                {a.business_rules.length} reglas · {a.apis.length} APIs
              </span>
            }
          >
            <div className="space-y-4">
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
                        (<RefChip refId={x.field_ref} />)
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
                    {x.entity_ref ? <RefChip refId={x.entity_ref} /> : null}
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
                    <RefChip refId={x.source_entity_ref} />{" "}
                    <Mono>{x.cardinality}</Mono>{" "}
                    <RefChip refId={x.target_entity_ref} />
                  </ItemRow>
                ))}
              </ModelBlock>
              <ModelBlock id="m-crud" title="CRUD" n={a.crud.length}>
                {a.crud.map((x) => (
                  <ItemRow key={x.id} id={x.id} origin={x.origin}>
                    <RefChip refId={x.entity_ref} />
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
            </div>
          </ArtifactSection>

          {/* 5. Análisis crítico */}
          <ArtifactSection
            id="sec-analysis"
            index="5"
            title="Análisis crítico"
            count={analysisTotal}
            open={disc.isOpen("sec-analysis")}
            onToggle={() => disc.toggle("sec-analysis")}
            forceRender={printMode}
            preview={
              <span>
                {analysis.ambiguities?.length ?? 0} ambigüedades ·{" "}
                {analysis.missing_info?.length ?? 0} faltantes ·{" "}
                {analysis.inconsistencies?.length ?? 0} inconsistencias ·{" "}
                {analysis.observations?.length ?? 0} observaciones
              </span>
            }
          >
            <div className="space-y-4">
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
                      <span className="ml-1 inline-flex flex-wrap gap-1">
                        {x.conflicting_refs.map((r) => (
                          <RefChip key={r} refId={r} />
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
        title="Responder preguntas al analista"
        questions={a.questions_for_analyst.map(
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
          <ValidationControls
            jobId={job.job_id}
            targetType="question"
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
    <div id={id} className="scroll-mt-28">
      <GroupLabel count={n}>{title}</GroupLabel>
      {n > 0 ? <DataList>{children}</DataList> : <EmptyHint>Vacío.</EmptyHint>}
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
    <DataRow
      id={id}
      right={
        <>
          {origin === "derived" ? <OriginBadge origin={origin} /> : null}
          <IdTag id={id} />
        </>
      }
    >
      {children}
    </DataRow>
  );
}
