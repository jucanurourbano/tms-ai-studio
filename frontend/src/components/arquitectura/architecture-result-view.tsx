"use client";

// CENTRO DE COMANDO del diseño de arquitectura. Mismo patrón que EF y Scrum
// (ver `components/ef/result-view.tsx`): cabecera + grid de tarjetas-sección,
// contenido en el panel lateral universal y PDF como documento lineal.
//
// Lo propio de esta vista son los DIAGRAMAS Mermaid: la librería se carga con
// `next/dynamic` (client-only) y solo cuando el diagrama se monta — es decir, al
// abrir su panel o al preparar la impresión. Nunca entra en el bundle global.

import {
  AlertTriangle,
  Boxes,
  Coins,
  DollarSign,
  Download,
  Eye,
  FileStack,
  Layers,
  MessagesSquare,
  Network,
  Plug,
  Printer,
  ShieldCheck,
  Target,
  Wrench,
} from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { ConfidenceBadge, JobStatusBadge, Mono } from "@/components/ef/badges";
import { ArtifactNavProvider } from "@/components/artifact/artifact-nav";
import {
  ArtifactPanel,
  type HubSection,
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
} from "@/components/artifact/primitives";
import { ArtifactSkeleton } from "@/components/artifact/artifact-skeleton";
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
import { makeRefResolver, type RefRoute } from "@/lib/artifact-refs";
import { filterByQuery, plural } from "@/lib/artifact-search";
import type { QuestionStatus } from "@/lib/types/ef";
import type {
  ArchitectureArtifact,
  ArchJobDetail,
  ArchValidationSummary,
  RiskSeverity,
} from "@/lib/types/arquitectura";
import { useArtifactHub } from "@/lib/use-artifact-hub";
import { useCelebrateOnTrue } from "@/lib/use-celebrate-on-true";
import { usePrintExpand } from "@/lib/use-print-expand";
import { useAuth } from "@/lib/auth/auth-context";
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

const SECTION_IDS = [
  "estilo",
  "componentes",
  "diagramas",
  "stack",
  "adrs",
  "contratos",
  "transversales",
  "analisis",
  "preguntas",
] as const;

/**
 * El diseño cita ids del EF y del Scrum (ENT-…, EPIC-…, REQ-N-…): no se resuelven
 * aquí porque no viven en este artefacto, y el chip lo dice en vez de fingir.
 */
const REF_ROUTES: RefRoute[] = [
  { prefix: "CMP-", sectionId: "componentes" },
  { prefix: "STK-", sectionId: "stack" },
  { prefix: "ADR-", sectionId: "adrs" },
  { prefix: "INT-", sectionId: "contratos", tabId: "integraciones" },
  { prefix: "CON-", sectionId: "contratos", tabId: "internos" },
  { prefix: "XC-", sectionId: "transversales" },
  { prefix: "Q-", sectionId: "preguntas" },
  { prefix: "RISK-", sectionId: "analisis", tabId: "riesgos" },
];

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
  const [questionMode, setQuestionMode] = useState<"lista" | "enfocado" | null>(
    null,
  );

  const hub = useArtifactHub(SECTION_IDS);
  const { printMode, printNow } = usePrintExpand();
  // Modo lectura: con acceso de solo lectura al módulo «arquitectura» se muestra
  // todo el contenido pero se retiran las acciones de escritura (responder,
  // confirmar/corregir, regenerar). El backend las rechazaría con 403.
  const { can } = useAuth();
  const puedeEditar = can("arquitectura", "full");
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
          `${refId} pertenece a las fuentes (EF o plan Scrum), no a este diseño.`,
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

  const blockingTotal = a.questions_for_architect.filter((q) => q.blocking).length;
  const blockingRemaining = a.questions_for_architect.filter(
    (q) => q.blocking && statusOf(q.id) === "pendiente",
  ).length;
  const pendingQuestions = a.questions_for_architect.filter(
    (q) => statusOf(q.id) === "pendiente",
  ).length;
  const mode = questionMode ?? (pendingQuestions > 0 ? "enfocado" : "lista");

  const contractsPending = a.integrations.filter((i) => !i.contract_known).length;
  const nfrPending = cov.nfr_total - cov.nfr_addressed;

  // Diagramas presentes en el artefacto: se usan para saber cuántos SVG debe
  // haber en el documento antes de lanzar la impresión.
  const diagramCodes = [a.diagrams.component?.code, a.diagrams.context?.code]
    .filter((c): c is string => !!c);
  const printWhenDiagramsReady = () =>
    document.querySelectorAll("#artifact-print-doc .mermaid-diagram svg")
      .length >= diagramCodes.length;

  const sheetQuestions = a.questions_for_architect.map(
    (q): SheetQuestion => ({
      id: q.id,
      question: q.question,
      reason: q.reason,
      blocking: q.blocking,
      linked_to_ref: q.linked_to_ref,
    }),
  );

  const questionControls = (id: string, onAnswered?: () => void) => (
    <ArchitectValidationControls
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

  const sections: HubSection[] = [
    {
      id: "estilo",
      title: "Estilo",
      printTitle: "Estilo arquitectónico",
      icon: <Layers />,
      searchable: false,
      tone: "teal",
      // Ondas: el estilo es criterio y justificación, no inventario.
      pattern: "waves",
      stat: style
        ? {
            value: a.context.size_class,
            label: `tamaño del alcance · ${style.chosen}`,
          }
        : { value: "—", label: "estilo sin decidir" },
      urgent: !style,
      insight: style ? (
        <span className="line-clamp-2">{style.rationale}</span>
      ) : (
        <span>Estilo arquitectónico sin decidir</span>
      ),
      render: () =>
        style ? (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <Badge className="bg-primary">{style.chosen}</Badge>
              <Badge variant="outline">tamaño {a.context.size_class}</Badge>
              {style.adr_ref && <RefChip refId={style.adr_ref} />}
              <ConfidenceBadge value={style.confidence} />
            </div>
            <p className="prose-measure text-sm leading-relaxed">
              {style.rationale}
            </p>
            <div>
              <GroupLabel>Perfil de alcance (determinista)</GroupLabel>
              <DataList>
                <DataRow>
                  {a.context.scope_profile.entities} entidades ·{" "}
                  {a.context.scope_profile.modules} módulos ·{" "}
                  {a.context.scope_profile.stories} historias ·{" "}
                  {a.context.scope_profile.integrations_detected} integraciones
                </DataRow>
              </DataList>
            </div>
            {a.context.bounded_contexts.length > 0 && (
              <div>
                <GroupLabel count={a.context.bounded_contexts.length}>
                  Contextos delimitados
                </GroupLabel>
                <DataList>
                  {a.context.bounded_contexts.map((bc) => (
                    <DataRow
                      key={bc.id}
                      id={bc.id}
                      right={
                        <>
                          {bc.source_refs.map((r) => (
                            <RefChip key={r} refId={r} />
                          ))}
                          <IdTag id={bc.id} />
                        </>
                      }
                    >
                      {bc.name}
                    </DataRow>
                  ))}
                </DataList>
              </div>
            )}
          </div>
        ) : (
          <EmptyHint>Estilo arquitectónico sin decidir.</EmptyHint>
        ),
    },

    {
      id: "componentes",
      title: "Componentes",
      icon: <Boxes />,
      count: a.components.length,
      tone: "sky",
      // Puntos: los componentes SON la estructura del sistema.
      pattern: "dots",
      stat: { value: a.components.length, label: "componentes del diseño" },
      insight: (
        <span className="line-clamp-2">
          {a.components.map((c) => c.name).join(" · ") || "Sin componentes"}
        </span>
      ),
      render: ({ query, forPrint }) => {
        const items = filterByQuery(forPrint ? "" : query, a.components, (c) => [
          c.id,
          c.name,
          c.type,
          c.layer,
          c.responsibility,
          ...c.depends_on,
        ]);
        if (items.length === 0)
          return (
            <EmptyHint warn={!query}>
              {query ? "Ningún componente coincide." : "Sin componentes."}
            </EmptyHint>
          );
        return (
          <div className="space-y-2">
            {items.map((c) => (
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
                  <span className="text-xs text-muted-foreground">· {c.layer}</span>
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
        );
      },
    },

    {
      id: "diagramas",
      title: "Diagramas",
      icon: <Network />,
      searchable: false,
      tone: "blue",
      stat: { value: diagramCodes.length, label: "diagramas Mermaid" },
      insight: <span>Componentes por capa y contexto del sistema</span>,
      tabs: [
        {
          id: "componentes",
          label: "Componentes por capa",
          render: () =>
            a.diagrams.component?.code ? (
              <MermaidDiagram code={a.diagrams.component.code} />
            ) : (
              <EmptyHint warn={false}>Sin diagrama de componentes.</EmptyHint>
            ),
        },
        {
          id: "contexto",
          label: "Contexto del sistema",
          render: () =>
            a.diagrams.context?.code ? (
              <MermaidDiagram code={a.diagrams.context.code} />
            ) : (
              <EmptyHint warn={false}>Sin diagrama de contexto.</EmptyHint>
            ),
        },
      ],
    },

    {
      id: "stack",
      title: "Stack",
      printTitle: "Stack tecnológico",
      icon: <Wrench />,
      count: a.stack.length,
      tone: "indigo",
      stat: { value: a.stack.length, label: "capas del stack de la casa" },
      insight: (
        <span className="line-clamp-2">
          {a.stack.map((s) => s.technology).join(" · ") ||
            "Sin stack recomendado"}
        </span>
      ),
      render: ({ query, forPrint }) => {
        const items = filterByQuery(forPrint ? "" : query, a.stack, (s) => [
          s.id,
          s.layer,
          s.technology,
          s.version,
          s.rationale,
          ...s.alternatives,
        ]);
        if (items.length === 0)
          return (
            <EmptyHint warn={!query}>
              {query ? "Nada coincide con la búsqueda." : "Sin stack recomendado."}
            </EmptyHint>
          );
        return (
          <div className="overflow-x-auto rounded-lg border">
            <table className="w-full border-collapse text-sm">
              <thead className="bg-muted/70 text-[11px] uppercase tracking-wide text-muted-foreground">
                <tr className="[&>th]:px-3 [&>th]:py-2 [&>th]:text-left [&>th]:font-semibold">
                  <th className="w-40">Capa</th>
                  <th>Tecnología</th>
                  <th>Alternativas</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/60">
                {items.map((s) => (
                  <tr
                    key={s.id}
                    id={`ref-${s.id}`}
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
        );
      },
    },

    {
      id: "adrs",
      title: "ADRs",
      printTitle: "Decisiones de arquitectura (ADRs)",
      icon: <FileStack />,
      count: a.adrs.length,
      tone: "violet",
      stat: { value: a.adrs.length, label: "decisiones registradas" },
      insight: (
        <span className="line-clamp-2">
          {a.adrs.map((adr) => adr.title).join(" · ") || "Sin ADRs"}
        </span>
      ),
      render: ({ query, forPrint }) => {
        const items = filterByQuery(forPrint ? "" : query, a.adrs, (adr) => [
          adr.id,
          adr.title,
          adr.decision,
          adr.context,
          adr.status,
          ...adr.consequences,
        ]);
        if (items.length === 0)
          return (
            <EmptyHint warn={false}>
              {query ? "Ningún ADR coincide." : "Sin ADRs adicionales."}
            </EmptyHint>
          );
        return (
          <div className="space-y-2">
            {items.map((adr) => (
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
        );
      },
    },

    {
      id: "contratos",
      title: "Integraciones y contratos",
      printTitle: "Integraciones y contratos",
      icon: <Plug />,
      count: a.integrations.length + a.contracts.length,
      tone: "cyan",
      stat: {
        value: a.integrations.length,
        label: `integraciones externas · ${plural(a.contracts.length, "contrato")}`,
      },
      urgent: contractsPending > 0,
      urgentLabel: contractsPending > 0 ? String(contractsPending) : undefined,
      insight:
        contractsPending > 0 ? (
          <span>
            {plural(contractsPending, "integración", "integraciones")} con contrato
            por definir
          </span>
        ) : a.integrations.length > 0 ? (
          <span>Todos los contratos externos conocidos</span>
        ) : (
          <span>Sin integraciones externas</span>
        ),
      tabs: [
        {
          id: "integraciones",
          label: "Integraciones",
          count: a.integrations.length,
          matchCount: (q) =>
            filterByQuery(q, a.integrations, (ig) => [
              ig.id,
              ig.name,
              ig.purpose,
              ig.direction,
              ig.protocol,
            ]).length,
          render: ({ query, forPrint }) => {
            const items = filterByQuery(
              forPrint ? "" : query,
              a.integrations,
              (ig) => [ig.id, ig.name, ig.purpose, ig.direction, ig.protocol],
            );
            if (items.length === 0)
              return (
                <EmptyHint warn={false}>
                  {query
                    ? "Ninguna integración coincide."
                    : "Sin integraciones externas."}
                </EmptyHint>
              );
            return (
              <div className="space-y-2">
                {items.map((ig) => (
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
            );
          },
        },
        {
          id: "internos",
          label: "Entre componentes",
          count: a.contracts.length,
          matchCount: (q) =>
            filterByQuery(q, a.contracts, (c) => [
              c.id,
              c.description,
              c.kind,
              c.from_ref,
              c.to_ref,
            ]).length,
          render: ({ query, forPrint }) => {
            const items = filterByQuery(
              forPrint ? "" : query,
              a.contracts,
              (c) => [c.id, c.description, c.kind, c.from_ref, c.to_ref],
            );
            if (items.length === 0)
              return (
                <EmptyHint warn={false}>
                  {query
                    ? "Ningún contrato coincide."
                    : "Sin contratos entre componentes."}
                </EmptyHint>
              );
            return (
              <DataList>
                {items.map((con) => (
                  <DataRow
                    key={con.id}
                    id={con.id}
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
                      <span className="text-muted-foreground">
                        {con.description}
                      </span>
                    </span>
                  </DataRow>
                ))}
              </DataList>
            );
          },
        },
      ],
    },

    {
      id: "transversales",
      title: "Transversales",
      printTitle: "Requisitos transversales",
      icon: <ShieldCheck />,
      count: a.cross_cutting.length,
      tone: "emerald",
      stat: { value: a.cross_cutting.length, label: "requisitos transversales" },
      urgent: nfrPending > 0,
      urgentLabel: nfrPending > 0 ? String(nfrPending) : undefined,
      insight:
        nfrPending > 0 ? (
          <span>{plural(nfrPending, "RNF", "RNF")} sin atender</span>
        ) : (
          <span className="line-clamp-2">
            {a.cross_cutting.map((xc) => xc.concern).join(" · ") ||
              "Sin requisitos transversales"}
          </span>
        ),
      render: ({ query, forPrint }) => {
        const items = filterByQuery(forPrint ? "" : query, a.cross_cutting, (xc) => [
          xc.id,
          xc.concern,
          xc.requirement,
          xc.approach,
        ]);
        if (items.length === 0)
          return (
            <EmptyHint warn={false}>
              {query
                ? "Nada coincide con la búsqueda."
                : "Sin requisitos transversales."}
            </EmptyHint>
          );
        return (
          <div className="space-y-2">
            {items.map((xc) => (
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
        );
      },
    },

    {
      id: "analisis",
      title: "Análisis",
      icon: <AlertTriangle />,
      count: a.analysis.risks.length,
      tone: "amber",
      // Diagonales: escrutinio — cobertura y riesgos del diseño.
      pattern: "lines",
      stat: { value: a.analysis.risks.length, label: "riesgos identificados" },
      urgent:
        cov.uncovered_epic_refs.length > 0 || cov.uncovered_entity_refs.length > 0,
      insight: (
        <span>
          Épicas {cov.epics_mapped}/{cov.epics_total} · entidades{" "}
          {cov.entities_mapped}/{cov.entities_total} · RNF {cov.nfr_addressed}/
          {cov.nfr_total}
        </span>
      ),
      tabs: [
        {
          id: "cobertura",
          label: "Cobertura",
          render: () => (
            <div className="rounded-lg border p-3 text-sm">
              <GroupLabel>Cobertura de trazabilidad</GroupLabel>
              <p>
                Épicas {cov.epics_mapped}/{cov.epics_total} · entidades{" "}
                {cov.entities_mapped}/{cov.entities_total} · RNF{" "}
                {cov.nfr_addressed}/{cov.nfr_total}
              </p>
              {cov.uncovered_epic_refs.length > 0 ||
              cov.uncovered_entity_refs.length > 0 ||
              cov.uncovered_nfr_refs.length > 0 ? (
                <div className="mt-1 space-y-0.5 text-xs text-amber-700">
                  <UncoveredLine label="Épicas" refs={cov.uncovered_epic_refs} />
                  <UncoveredLine
                    label="Entidades"
                    refs={cov.uncovered_entity_refs}
                  />
                  <UncoveredLine label="RNF" refs={cov.uncovered_nfr_refs} />
                </div>
              ) : (
                <p className="mt-1 text-xs text-emerald-700">
                  Todo lo que venía del EF y del plan quedó cubierto.
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
              r.mitigation,
            ]).length,
          render: ({ query, forPrint }) => {
            const items = filterByQuery(
              forPrint ? "" : query,
              a.analysis.risks,
              (r) => [r.id, r.description, r.severity, r.mitigation],
            );
            if (items.length === 0)
              return <EmptyHint warn={false}>Sin riesgos.</EmptyHint>;
            return (
              <div className="space-y-2">
                {items.map((r) => (
                  <div
                    key={r.id}
                    id={`ref-${r.id}`}
                    className="print-atom rounded-lg border p-3"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <IdTag id={r.id} />
                      <Badge variant="outline" className={SEVERITY_STYLE[r.severity]}>
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
            );
          },
        },
      ],
    },

    {
      id: "preguntas",
      title: "Preguntas",
      printTitle: "Preguntas al Arquitecto",
      icon: <MessagesSquare />,
      count: a.questions_for_architect.length,
      tone: "rose",
      stat: {
        value: a.questions_for_architect.length,
        label: `preguntas al Arquitecto · ${plural(blockingTotal, "bloqueante")}`,
      },
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
          ? a.questions_for_architect
          : onlyBlocking
            ? a.questions_for_architect.filter((q) => q.blocking)
            : a.questions_for_architect;
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
  ];

  return (
    <ArtifactNavProvider
      navigateToRef={navigateToRef}
      canNavigateToRef={canNavigateToRef}
    >
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
            {
              label: "cobertura",
              value: `${Math.round(a.metrics.coverage * 100)}%`,
            },
          ]}
        />
        <PrintFooter title="Diseño de Arquitectura" />

        {/* Barra superior de afinamiento + semáforo */}
        <div className="sticky top-0 z-10 border-b bg-background/95 px-6 py-4 backdrop-blur print:hidden">
          {/* (a) Identidad: qué diseño es, de qué fuentes sale y en qué estado. */}
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2 text-sm">
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
              {ready ? "Listo para el Agente BD" : "Pendiente de afinamiento"}
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

            {/* Acciones agrupadas: preguntas | exportes | regenerar. */}
            <div className="ml-auto">
              <HeaderActions>
              {puedeEditar && a.questions_for_architect.length > 0 && (
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
                // Espera a que los SVG de Mermaid estén en el documento: el PDF
                // de Arquitectura sin diagramas no sirve de nada.
                onClick={() => printNow(printWhenDiagramsReady)}
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
              </ActionGroup>
              {puedeEditar && (
                <ActionGroup>
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
                      Costo estimado: ~${a.metrics.cost.toFixed(4)} (similar al
                      diseño anterior). Esta acción consume tokens de la API.
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
        </div>

        {/* (b) Mini-stats, con el estado separado a la derecha. */}
        <div className="border-b px-6 py-5 print:hidden">
          <div className="flex flex-wrap items-center gap-x-8 gap-y-4">
            <StatRow>
              <Stat
                icon={<Boxes />}
                value={a.components.length}
                label="componentes"
              />
              <Stat icon={<FileStack />} value={a.adrs.length} label="ADRs" />
              <Stat
                icon={<Plug />}
                value={a.integrations.length}
                label="integraciones"
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

        <ArtifactPanel hub={hub} sections={sections} module="arquitectura" />
        <ArtifactPrintDoc sections={sections} active={printMode} />
      </div>
    </ArtifactNavProvider>
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
