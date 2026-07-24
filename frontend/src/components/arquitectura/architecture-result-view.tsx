"use client";

import {
  Boxes,
  Coins,
  Download,
  DollarSign,
  FileStack,
  MessagesSquare,
  Plug,
  Printer,
  Target,
} from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { ConfidenceBadge, JobStatusBadge, Mono } from "@/components/ef/badges";
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
import { ArchitectValidationControls } from "@/components/arquitectura/validation-controls";
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
import { ApiError } from "@/lib/api/client";
import { arquitecturaApi } from "@/lib/api/arquitectura";
import type { QuestionStatus } from "@/lib/types/ef";
import type {
  ArchitectureArtifact,
  ArchJobDetail,
  ArchValidationSummary,
  RiskSeverity,
} from "@/lib/types/arquitectura";
import { useCelebrateOnTrue } from "@/lib/use-celebrate-on-true";
import { useDisclosure } from "@/lib/use-disclosure";
import { usePersistentState } from "@/lib/use-persistent-state";
import { usePrintExpand } from "@/lib/use-print-expand";
import { cn } from "@/lib/utils";

// Mermaid: import dinámico client-only y lazy SOLO en esta vista (fuera del
// bundle global). Se carga cuando se monta el diagrama.
const MermaidDiagram = dynamic(
  () =>
    import("@/components/artifact/mermaid-diagram").then((m) => m.MermaidDiagram),
  {
    ssr: false,
    loading: () => (
      <div className="h-40 animate-pulse rounded-lg bg-muted/40" aria-hidden />
    ),
  },
);

const SEVERITY_STYLE: Record<RiskSeverity, string> = {
  alta: "border-red-300 bg-red-50 text-red-700",
  media: "border-amber-300 bg-amber-50 text-amber-700",
  baja: "border-slate-300 bg-slate-50 text-slate-600",
};

function download(content: string, filename: string, type: string) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function ArchitectureResultView({ job }: { job: ArchJobDetail }) {
  const router = useRouter();
  const [artifact, setArtifact] = useState<ArchitectureArtifact | null>(null);
  const [summary, setSummary] = useState<ArchValidationSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [onlyBlocking, setOnlyBlocking] = useState(false);
  const [refining, setRefining] = useState(false);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [indexCollapsed, setIndexCollapsed] = usePersistentState(
    "artifact:index-collapsed",
    false,
  );
  const disc = useDisclosure(2);
  const { printMode, printNow } = usePrintExpand();
  const celebrate = useCelebrateOnTrue(
    summary?.ready_for_next_stage ?? false,
    summary != null,
  );

  const loadAll = useCallback(() => {
    Promise.all([
      arquitecturaApi.getArtifact(job.job_id),
      arquitecturaApi.getValidationSummary(job.job_id),
    ])
      .then(([a, s]) => {
        setArtifact(a);
        setSummary(s);
        setError(null);
      })
      .catch((err) =>
        setError(
          err instanceof ApiError ? err.message : "No se pudo cargar el diseño.",
        ),
      )
      .finally(() => setLoading(false));
  }, [job.job_id]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const reloadSummary =
    useCallback(async (): Promise<ArchValidationSummary | null> => {
      try {
        const s = await arquitecturaApi.getValidationSummary(job.job_id);
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

  async function doRefine() {
    setRefining(true);
    try {
      const child = await arquitecturaApi.refine(job.job_id);
      toast.success("Regeneración iniciada (job hijo)");
      router.push(`/agents/arquitectura/jobs/${child.job_id}`);
    } catch (err) {
      toast.error("No se pudo regenerar", {
        description: err instanceof ApiError ? err.message : undefined,
      });
    } finally {
      setRefining(false);
    }
  }

  if (loading) return <ArtifactSkeleton />;
  if (error || !artifact) {
    return (
      <div className="p-6 text-sm text-red-600">
        {error ?? "Diseño no disponible."}
      </div>
    );
  }

  const a = artifact;
  const ready = summary?.ready_for_next_stage ?? false;
  const style = a.architecture_style;
  const cov = a.analysis.coverage;
  const canRefine = answered >= 1;

  const questions = onlyBlocking
    ? a.questions_for_architect.filter((q) => q.blocking)
    : a.questions_for_architect;
  const blockingTotal = a.questions_for_architect.filter((q) => q.blocking).length;
  const blockingRemaining = a.questions_for_architect.filter(
    (q) => q.blocking && statusOf(q.id) === "pendiente",
  ).length;

  const indexSections: IndexSection[] = [
    { id: "sec-style", label: "Estilo" },
    { id: "sec-components", label: "Componentes", count: a.components.length },
    { id: "sec-diagrams", label: "Diagramas" },
    { id: "sec-stack", label: "Stack", count: a.stack.length },
    { id: "sec-adrs", label: "ADRs", count: a.adrs.length },
    {
      id: "sec-integrations",
      label: "Integraciones",
      count: a.integrations.length,
    },
    { id: "sec-contracts", label: "Contratos", count: a.contracts.length },
    { id: "sec-crosscutting", label: "Transversales", count: a.cross_cutting.length },
    {
      id: "sec-analysis",
      label: "Análisis",
      count: a.analysis.risks.length,
    },
    {
      id: "sec-questions",
      label: "Preguntas",
      count: a.questions_for_architect.length,
      meta: `${blockingTotal} bloq.`,
    },
  ];

  return (
    <div className="flex h-full flex-col">
      <PrintCover
        kind="Diseño de Arquitectura"
        title={style ? `Arquitectura ${style.chosen}` : "Diseño de arquitectura"}
        subtitle="Componentes, stack, ADRs, integraciones, contratos, requisitos transversales y diagramas."
        version="1.0.0"
        stats={[
          { label: "componentes", value: String(a.components.length) },
          { label: "ADRs", value: String(a.adrs.length) },
          { label: "integraciones", value: String(a.integrations.length) },
          { label: "cobertura", value: `${Math.round(a.metrics.coverage * 100)}%` },
        ]}
      />
      <PrintToc
        items={[
          "Estilo arquitectónico",
          "Componentes",
          "Diagramas",
          "Stack tecnológico",
          "ADRs",
          "Integraciones",
          "Contratos",
          "Requisitos transversales",
          "Análisis",
          "Preguntas al Arquitecto",
        ]}
      />
      <PrintFooter title="Diseño de Arquitectura" />

      {/* Barra superior de afinamiento + semáforo */}
      <div className="sticky top-0 z-10 border-b bg-background/95 px-6 py-3 backdrop-blur print:hidden">
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <span className="font-heading font-semibold">Arquitectura v1.0.0</span>
          <Badge variant="outline">
            {job.parent_job_id ? "v2 · afinamiento" : "v1 · original"}
          </Badge>
          {job.input_job_id && (
            <Link
              href={`/agents/scrum/jobs/${job.input_job_id}`}
              className="text-xs text-muted-foreground underline-offset-2 hover:text-primary hover:underline"
            >
              plan Scrum (<Mono>{job.input_job_id}</Mono>)
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
          <span className="text-xs text-muted-foreground">{answered} respondidas</span>
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
            {ready ? "Listo para el Agente BD" : "Pendiente de afinamiento"}
          </span>

          <div className="ml-auto flex flex-wrap gap-2">
            {a.questions_for_architect.length > 0 && (
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
              variant="outline"
              size="sm"
              className="gap-1.5"
              onClick={() =>
                download(
                  JSON.stringify(a, null, 2),
                  `arquitectura-artifact-${job.job_id}.json`,
                  "application/json",
                )
              }
            >
              <Download className="h-3.5 w-3.5" />
              JSON
            </Button>
            <Dialog>
              <DialogTrigger
                render={
                  <Button size="sm" disabled={!canRefine}>
                    Regenerar diseño afinado
                  </Button>
                }
              />
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Regenerar diseño afinado</DialogTitle>
                  <DialogDescription>
                    Se creará un diseño hijo reinyectando las respuestas del
                    Arquitecto y se ejecutará el modelo real.
                  </DialogDescription>
                </DialogHeader>
                <div className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800">
                  Costo estimado: ~${a.metrics.cost.toFixed(4)} (similar al diseño
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
      </div>

      {/* Cabecera: estado + mini-stats */}
      <div className="border-b px-6 py-4">
        <div className="mb-3">
          <JobStatusBadge status={job.status} />
        </div>
        <StatRow>
          <Stat icon={<Boxes />} value={a.components.length} label="componentes" />
          <Stat icon={<FileStack />} value={a.adrs.length} label="ADRs" />
          <Stat icon={<Plug />} value={a.integrations.length} label="integraciones" />
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

        <div className="min-w-0 space-y-6 stagger-children">
          {/* 1. Estilo arquitectónico */}
          <ArtifactSection
            id="sec-style"
            index="1"
            title="Estilo arquitectónico"
            open={disc.isOpen("sec-style")}
            onToggle={() => disc.toggle("sec-style")}
            forceRender={printMode}
            preview={
              <span>
                {style
                  ? `${style.chosen} · tamaño ${a.context.size_class}`
                  : "Sin decidir"}
              </span>
            }
          >
            {style ? (
              <div className="space-y-2">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge className="bg-primary">{style.chosen}</Badge>
                  <Badge variant="outline">tamaño {a.context.size_class}</Badge>
                  {style.adr_ref && <RefChip refId={style.adr_ref} />}
                  <ConfidenceBadge value={style.confidence} />
                </div>
                <p className="text-sm">{style.rationale}</p>
                <p className="text-xs text-muted-foreground">
                  Perfil de alcance: {a.context.scope_profile.entities} entidades ·{" "}
                  {a.context.scope_profile.modules} módulos ·{" "}
                  {a.context.scope_profile.stories} historias ·{" "}
                  {a.context.scope_profile.integrations_detected} integraciones.
                </p>
              </div>
            ) : (
              <EmptyHint>Estilo arquitectónico sin decidir.</EmptyHint>
            )}
          </ArtifactSection>

          {/* 2. Componentes */}
          <ArtifactSection
            id="sec-components"
            index="2"
            title="Componentes"
            count={a.components.length}
            open={disc.isOpen("sec-components")}
            onToggle={() => disc.toggle("sec-components")}
            forceRender={printMode}
            preview={
              <span className="line-clamp-2">
                {a.components.map((c) => c.name).join(" · ") ||
                  "Sin componentes"}
              </span>
            }
          >
            {a.components.length > 0 ? (
              <div className="space-y-2">
                {a.components.map((c) => (
                  <div
                    key={c.id}
                    id={`ref-${c.id}`}
                    className="print-atom rounded-lg border p-3"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <IdTag id={c.id} />
                      <Badge variant="outline" className="text-muted-foreground">
                        {c.type}
                      </Badge>
                      <span className="text-sm font-medium">{c.name}</span>
                      <span className="text-xs text-muted-foreground">
                        · {c.layer}
                      </span>
                      <ConfidenceBadge value={c.confidence} />
                    </div>
                    <p className="mt-1.5 text-sm">{c.responsibility}</p>
                    <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
                      {c.depends_on.length > 0 && (
                        <span className="inline-flex flex-wrap items-center gap-1">
                          depende de:{" "}
                          {c.depends_on.map((d) => (
                            <RefChip key={d} refId={d} />
                          ))}
                        </span>
                      )}
                      <RefList label="épicas" refs={c.source_refs.epic_refs} />
                      <RefList label="historias" refs={c.source_refs.story_refs} />
                      <RefList label="entidades" refs={c.source_refs.entity_refs} />
                      <RefList label="APIs" refs={c.source_refs.api_refs} />
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyHint>Sin componentes.</EmptyHint>
            )}
          </ArtifactSection>

          {/* 3. Diagramas */}
          <ArtifactSection
            id="sec-diagrams"
            index="3"
            title="Diagramas"
            open={disc.isOpen("sec-diagrams")}
            onToggle={() => disc.toggle("sec-diagrams")}
            forceRender={printMode}
            preview={
              <span>Componentes por capa y contexto del sistema (Mermaid)</span>
            }
          >
            <div className="space-y-4">
              <div>
                <GroupLabel>Componentes por capa</GroupLabel>
                {a.diagrams.component?.code ? (
                  <MermaidDiagram code={a.diagrams.component.code} />
                ) : (
                  <EmptyHint warn={false}>Sin diagrama de componentes.</EmptyHint>
                )}
              </div>
              <div>
                <GroupLabel>Contexto del sistema</GroupLabel>
                {a.diagrams.context?.code ? (
                  <MermaidDiagram code={a.diagrams.context.code} />
                ) : (
                  <EmptyHint warn={false}>Sin diagrama de contexto.</EmptyHint>
                )}
              </div>
            </div>
          </ArtifactSection>

          {/* 4. Stack */}
          <ArtifactSection
            id="sec-stack"
            index="4"
            title="Stack tecnológico"
            count={a.stack.length}
            open={disc.isOpen("sec-stack")}
            onToggle={() => disc.toggle("sec-stack")}
            forceRender={printMode}
            preview={
              <span className="line-clamp-2">
                {a.stack.map((s) => s.technology).join(" · ") ||
                  "Sin stack recomendado"}
              </span>
            }
          >
            {a.stack.length > 0 ? (
              <div className="overflow-x-auto rounded-lg border">
                <table className="w-full border-collapse text-sm">
                  <thead className="bg-muted/70 text-[11px] uppercase tracking-wide text-muted-foreground">
                    <tr className="[&>th]:px-3 [&>th]:py-2 [&>th]:text-left [&>th]:font-semibold">
                      <th className="w-48">Capa</th>
                      <th>Tecnología</th>
                      <th>Alternativas</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/60">
                    {a.stack.map((s) => (
                      <tr
                        key={s.id}
                        className="odd:bg-muted/20 [&>td]:px-3 [&>td]:py-2 [&>td]:align-top"
                      >
                        <td className="font-mono text-xs text-muted-foreground">
                          {s.layer}
                        </td>
                        <td>
                          <span className="font-medium">{s.technology}</span>
                          {s.version ? (
                            <span className="text-muted-foreground"> {s.version}</span>
                          ) : null}
                          <div className="text-xs text-muted-foreground">
                            {s.rationale}
                          </div>
                        </td>
                        <td className="text-xs text-muted-foreground">
                          {s.alternatives.join(", ") || "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <EmptyHint>Sin stack recomendado.</EmptyHint>
            )}
          </ArtifactSection>

          {/* 5. ADRs */}
          <ArtifactSection
            id="sec-adrs"
            index="5"
            title="ADRs"
            count={a.adrs.length}
            open={disc.isOpen("sec-adrs")}
            onToggle={() => disc.toggle("sec-adrs")}
            forceRender={printMode}
            preview={
              <span className="line-clamp-2">
                {a.adrs.map((adr) => adr.title).join(" · ") || "Sin ADRs"}
              </span>
            }
          >
            {a.adrs.length > 0 ? (
              <div className="space-y-2">
                {a.adrs.map((adr) => (
                  <div
                    key={adr.id}
                    id={`ref-${adr.id}`}
                    className="print-atom rounded-lg border p-3"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <IdTag id={adr.id} />
                      <span className="text-sm font-medium">{adr.title}</span>
                      <Badge variant="outline" className="text-muted-foreground">
                        {adr.status}
                      </Badge>
                      <ConfidenceBadge value={adr.confidence} />
                    </div>
                    <p className="mt-1.5 text-sm">{adr.decision}</p>
                    <p className="text-xs text-muted-foreground">{adr.context}</p>
                    {adr.consequences.length > 0 && (
                      <ul className="mt-1 list-disc pl-5 text-xs text-muted-foreground">
                        {adr.consequences.map((cs, i) => (
                          <li key={i}>{cs}</li>
                        ))}
                      </ul>
                    )}
                    {adr.source_refs.length > 0 && (
                      <div className="mt-1.5 flex flex-wrap items-center gap-1 text-xs text-muted-foreground">
                        origen:{" "}
                        {adr.source_refs.map((r) => (
                          <RefChip key={r} refId={r} />
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <EmptyHint warn={false}>Sin ADRs adicionales.</EmptyHint>
            )}
          </ArtifactSection>

          {/* 6. Integraciones */}
          <ArtifactSection
            id="sec-integrations"
            index="6"
            title="Integraciones"
            count={a.integrations.length}
            open={disc.isOpen("sec-integrations")}
            onToggle={() => disc.toggle("sec-integrations")}
            forceRender={printMode}
            preview={
              <span>
                {a.integrations.length > 0
                  ? `${a.integrations.filter((i) => !i.contract_known).length} con contrato por definir`
                  : "Sin integraciones externas"}
              </span>
            }
          >
            {a.integrations.length > 0 ? (
              <div className="space-y-2">
                {a.integrations.map((ig) => (
                  <div
                    key={ig.id}
                    id={`ref-${ig.id}`}
                    className="print-atom rounded-lg border p-3"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <IdTag id={ig.id} />
                      <span className="text-sm font-medium">{ig.name}</span>
                      <Badge variant="outline" className="text-muted-foreground">
                        {ig.direction} · {ig.protocol}
                      </Badge>
                      {ig.contract_known ? (
                        <Badge
                          variant="outline"
                          className="border-emerald-300 bg-emerald-50 text-emerald-700"
                        >
                          contrato conocido
                        </Badge>
                      ) : (
                        <Badge
                          variant="outline"
                          className="border-amber-300 bg-amber-50 text-amber-700"
                        >
                          contrato por definir
                        </Badge>
                      )}
                      <ConfidenceBadge value={ig.confidence} />
                    </div>
                    <p className="mt-1.5 text-sm">{ig.purpose}</p>
                    {ig.source_refs.length > 0 && (
                      <div className="mt-1.5 flex flex-wrap items-center gap-1 text-xs text-muted-foreground">
                        origen:{" "}
                        {ig.source_refs.map((r) => (
                          <RefChip key={r} refId={r} />
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <EmptyHint warn={false}>Sin integraciones externas.</EmptyHint>
            )}
          </ArtifactSection>

          {/* 7. Contratos */}
          <ArtifactSection
            id="sec-contracts"
            index="7"
            title="Contratos"
            count={a.contracts.length}
            open={disc.isOpen("sec-contracts")}
            onToggle={() => disc.toggle("sec-contracts")}
            forceRender={printMode}
            preview={
              <span>
                {a.contracts.length > 0
                  ? `${a.contracts.length} contrato${a.contracts.length !== 1 ? "s" : ""} entre componentes`
                  : "Sin contratos entre componentes"}
              </span>
            }
          >
            {a.contracts.length > 0 ? (
              <DataList>
                {a.contracts.map((con) => (
                  <DataRow
                    key={con.id}
                    right={
                      <Badge variant="outline" className="text-muted-foreground">
                        {con.kind}
                      </Badge>
                    }
                  >
                    <span className="inline-flex flex-wrap items-center gap-1.5">
                      <RefChip refId={con.from_ref} />
                      <span className="text-muted-foreground">→</span>
                      <RefChip refId={con.to_ref} />
                      <span className="text-muted-foreground">{con.description}</span>
                    </span>
                  </DataRow>
                ))}
              </DataList>
            ) : (
              <EmptyHint warn={false}>Sin contratos entre componentes.</EmptyHint>
            )}
          </ArtifactSection>

          {/* 8. Transversales */}
          <ArtifactSection
            id="sec-crosscutting"
            index="8"
            title="Requisitos transversales"
            count={a.cross_cutting.length}
            open={disc.isOpen("sec-crosscutting")}
            onToggle={() => disc.toggle("sec-crosscutting")}
            forceRender={printMode}
            preview={
              <span className="line-clamp-2">
                {a.cross_cutting.map((xc) => xc.concern).join(" · ") ||
                  "Sin requisitos transversales"}
              </span>
            }
          >
            {a.cross_cutting.length > 0 ? (
              <div className="space-y-2">
                {a.cross_cutting.map((xc) => (
                  <div
                    key={xc.id}
                    id={`ref-${xc.id}`}
                    className="print-atom rounded-lg border p-3"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <IdTag id={xc.id} />
                      <Badge className="bg-primary">{xc.concern}</Badge>
                      <ConfidenceBadge value={xc.confidence} />
                    </div>
                    <p className="mt-1.5 text-sm">{xc.requirement}</p>
                    <p className="text-xs text-muted-foreground">{xc.approach}</p>
                    {xc.source_refs.length > 0 && (
                      <div className="mt-1.5 flex flex-wrap items-center gap-1 text-xs text-muted-foreground">
                        origen:{" "}
                        {xc.source_refs.map((r) => (
                          <RefChip key={r} refId={r} />
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <EmptyHint warn={false}>Sin requisitos transversales.</EmptyHint>
            )}
          </ArtifactSection>

          {/* 9. Análisis */}
          <ArtifactSection
            id="sec-analysis"
            index="9"
            title="Análisis"
            count={a.analysis.risks.length}
            open={disc.isOpen("sec-analysis")}
            onToggle={() => disc.toggle("sec-analysis")}
            forceRender={printMode}
            preview={
              <span>
                Épicas {cov.epics_mapped}/{cov.epics_total} · entidades{" "}
                {cov.entities_mapped}/{cov.entities_total} · RNF{" "}
                {cov.nfr_addressed}/{cov.nfr_total} · {a.analysis.risks.length}{" "}
                riesgos
              </span>
            }
          >
            <div className="space-y-4">
              <div className="rounded-lg border p-3 text-sm">
                <GroupLabel>Cobertura de trazabilidad</GroupLabel>
                <p>
                  Épicas {cov.epics_mapped}/{cov.epics_total} · entidades{" "}
                  {cov.entities_mapped}/{cov.entities_total} · RNF{" "}
                  {cov.nfr_addressed}/{cov.nfr_total}
                </p>
                {(cov.uncovered_epic_refs.length > 0 ||
                  cov.uncovered_entity_refs.length > 0 ||
                  cov.uncovered_nfr_refs.length > 0) && (
                  <div className="mt-1 space-y-0.5 text-xs text-amber-700">
                    <UncoveredLine label="Épicas" refs={cov.uncovered_epic_refs} />
                    <UncoveredLine
                      label="Entidades"
                      refs={cov.uncovered_entity_refs}
                    />
                    <UncoveredLine label="RNF" refs={cov.uncovered_nfr_refs} />
                  </div>
                )}
              </div>

              <div>
                <GroupLabel count={a.analysis.risks.length}>Riesgos</GroupLabel>
                {a.analysis.risks.length > 0 ? (
                  <div className="space-y-2">
                    {a.analysis.risks.map((r) => (
                      <div key={r.id} className="print-atom rounded-lg border p-3">
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
                        <p className="mt-1.5 text-sm">{r.description}</p>
                        {r.mitigation && (
                          <p className="text-xs text-muted-foreground">
                            Mitigación: {r.mitigation}
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <EmptyHint warn={false}>Sin riesgos.</EmptyHint>
                )}
              </div>
            </div>
          </ArtifactSection>

          {/* 10. Preguntas al Arquitecto */}
          <ArtifactSection
            id="sec-questions"
            index="10"
            title="Preguntas al Arquitecto"
            count={a.questions_for_architect.length}
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
                      <ArchitectValidationControls
                        jobId={job.job_id}
                        targetId={q.id}
                        status={statusOf(q.id)}
                        respuesta={respuestaOf(q.id)}
                        onChanged={() => void reloadSummary()}
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
                {onlyBlocking ? "Sin preguntas bloqueantes." : "Sin preguntas."}
              </EmptyHint>
            )}
          </ArtifactSection>
        </div>
      </div>

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
        title="Responder preguntas al Arquitecto"
        questions={a.questions_for_architect.map(
          (q): SheetQuestion => ({
            id: q.id,
            question: q.question,
            reason: q.reason,
            blocking: q.blocking,
            linked_to_ref: q.linked_to_ref,
          }),
        )}
        statusOf={statusOf}
        renderControls={(q, onAnswered) => (
          <ArchitectValidationControls
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

function RefList({ label, refs }: { label: string; refs: string[] }) {
  if (!refs || refs.length === 0) return null;
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      {label}:{" "}
      {refs.map((r) => (
        <RefChip key={r} refId={r} />
      ))}
    </span>
  );
}

function UncoveredLine({ label, refs }: { label: string; refs: string[] }) {
  if (!refs || refs.length === 0) return null;
  return (
    <p className="inline-flex flex-wrap items-center gap-1">
      ⚠ {label} sin cubrir:{" "}
      {refs.map((r) => (
        <RefChip key={r} refId={r} />
      ))}
    </p>
  );
}

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
