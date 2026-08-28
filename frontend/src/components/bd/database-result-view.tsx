"use client";

// CENTRO DE COMANDO del modelo de datos. Mismo patrón que EF, Scrum y
// Arquitectura: cabecera + grid de tarjetas-sección, contenido en el panel
// lateral universal y PDF como documento lineal.
//
// Lo propio de esta vista son dos cosas. El **diagrama ER** en Mermaid, cargado
// con `next/dynamic` (client-only) solo cuando se monta. Y el **DDL**, que no es
// documentación: es lo que alguien va a ejecutar contra una base de datos, así
// que se puede copiar, descargar y — por el diseño de doble nivel de tipo — pedir
// en otro motor sin volver a llamar al modelo.

import {
  AlertTriangle,
  BookOpen,
  Boxes,
  Check,
  Coins,
  Copy,
  Database,
  DollarSign,
  Download,
  Eye,
  FileCode,
  Gavel,
  KeyRound,
  Layers,
  ListChecks,
  MessagesSquare,
  Network,
  Printer,
  ShieldCheck,
  Sprout,
  Table2,
  Target,
} from "lucide-react";
import dynamic from "next/dynamic";
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
import { ValidationHint } from "@/components/artifact/validation-controls";
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
  PrintValidationState,
  RefChip,
  Stat,
  StatRow,
} from "@/components/artifact/primitives";
import { DbaValidationControls } from "@/components/bd/validation-controls";
import { ConfidenceBadge, JobStatusBadge, Mono } from "@/components/ef/badges";
import {
  ReconciliationBadge,
  ReconciliationDetail,
  ReconciliationSummaryBar,
} from "@/components/inventario/reconciliation-badge";
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
import { bdApi } from "@/lib/api/bd";
import { ApiError } from "@/lib/api/client";
import { makeRefResolver } from "@/lib/artifact-refs";
import { BD_REF_ROUTES } from "@/lib/bd-refs";
import { filterByQuery, plural } from "@/lib/artifact-search";
import { useAuth } from "@/lib/auth/auth-context";
import type { RiskSeverity } from "@/lib/types/arquitectura";
import type {
  DatabaseArtifact,
  DbColumn,
  DbEngine,
  DbJobDetail,
  DbTable,
  DbValidationSummary,
} from "@/lib/types/bd";
import type { QuestionStatus } from "@/lib/types/ef";
import { useArtifactHub } from "@/lib/use-artifact-hub";
import { useCelebrateOnTrue } from "@/lib/use-celebrate-on-true";
import { usePrintExpand } from "@/lib/use-print-expand";
import { cn } from "@/lib/utils";

// Mermaid: import dinámico client-only y lazy SOLO en esta vista (fuera del
// bundle global). Se carga cuando se monta el diagrama.
const MermaidDiagram = dynamic(
  () =>
    import("@/components/artifact/mermaid-diagram").then(
      (m) => m.MermaidDiagram,
    ),
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

const KIND_LABEL: Record<string, string> = {
  entity: "entidad",
  junction: "puente",
  catalog: "catálogo",
  audit: "auditoría",
};

const ENFORCEMENT_LABEL: Record<string, string> = {
  declarative: "en el esquema",
  application: "en la aplicación",
  trigger: "con trigger",
};

const ENFORCEMENT_STYLE: Record<string, string> = {
  declarative: "border-emerald-300 bg-emerald-50 text-emerald-700",
  application: "border-sky-300 bg-sky-50 text-sky-700",
  trigger: "border-amber-300 bg-amber-50 text-amber-700",
};

const ENGINES: { value: DbEngine; label: string }[] = [
  { value: "postgresql", label: "PostgreSQL" },
  { value: "sqlserver", label: "SQL Server" },
  { value: "oracle", label: "Oracle" },
  { value: "mysql", label: "MySQL" },
];

const SECTION_IDS = [
  "tablas",
  "diagrama",
  "ddl",
  "diccionario",
  "semilla",
  "reglas",
  "decisiones",
  "validacion",
  "analisis",
  "preguntas",
] as const;

function download(content: string, filename: string, type: string) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function DatabaseResultView({ job }: { job: DbJobDetail }) {
  const router = useRouter();
  const [artifact, setArtifact] = useState<DatabaseArtifact | null>(null);
  const [summary, setSummary] = useState<DbValidationSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refining, setRefining] = useState(false);
  const [questionMode, setQuestionMode] = useState<"lista" | "enfocado" | null>(
    null,
  );
  // Motor con el que se muestra el DDL. Cambiarlo re-renderiza en el backend
  // sin coste de modelo; `null` = el motor de registro del artefacto.
  const [ddlEngine, setDdlEngine] = useState<DbEngine | null>(null);
  const [ddlSql, setDdlSql] = useState<string | null>(null);
  const [ddlLoading, setDdlLoading] = useState(false);

  const hub = useArtifactHub(SECTION_IDS);
  const { printMode, printNow } = usePrintExpand();
  // Modo lectura: con acceso de solo lectura al módulo «bd» se muestra todo el
  // contenido pero se retiran las acciones de escritura. El backend las
  // rechazaría con 403.
  const { can } = useAuth();
  const puedeEditar = can("bd", "full");
  const celebrate = useCelebrateOnTrue(
    summary?.ready_for_next_stage ?? false,
    summary != null,
  );

  const loadAll = useCallback(() => {
    Promise.all([
      bdApi.getArtifact(job.job_id),
      bdApi.getValidationSummary(job.job_id),
    ])
      .then(([a, s]) => {
        setArtifact(a);
        setSummary(s);
        setError(null);
      })
      .catch((err) =>
        setError(
          err instanceof ApiError ? err.message : "No se pudo cargar el modelo.",
        ),
      )
      .finally(() => setLoading(false));
  }, [job.job_id]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const reloadSummary = useCallback(async (): Promise<DbValidationSummary | null> => {
    try {
      const s = await bdApi.getValidationSummary(job.job_id);
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

  const resolveRef = useMemo(() => makeRefResolver(BD_REF_ROUTES), []);
  const canNavigateToRef = useCallback(
    (refId: string) => resolveRef(refId) !== null,
    [resolveRef],
  );
  const navigateToRef = useCallback(
    (refId: string) => {
      const target = resolveRef(refId);
      if (!target) {
        toast.info(
          `${refId} pertenece a las fuentes (EF o diseño de arquitectura), no a este modelo.`,
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

  /** Pide el DDL en otro motor: es un render en el backend, no una regeneración. */
  const cambiarMotorDdl = useCallback(
    async (engine: DbEngine | null) => {
      setDdlEngine(engine);
      if (engine === null) {
        setDdlSql(null);
        return;
      }
      setDdlLoading(true);
      try {
        const data = await bdApi.getDdl(job.job_id, engine);
        setDdlSql(data.sql);
      } catch (err) {
        toast.error("No se pudo generar el DDL", {
          description: err instanceof ApiError ? err.message : undefined,
        });
        setDdlEngine(null);
      } finally {
        setDdlLoading(false);
      }
    },
    [job.job_id],
  );

  async function doRefine() {
    setRefining(true);
    try {
      const child = await bdApi.refine(job.job_id);
      toast.success("Regeneración iniciada (job hijo)");
      router.push(`/agents/bd/jobs/${child.job_id}`);
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
        {error ?? "Modelo no disponible."}
      </div>
    );
  }

  const a = artifact;
  const ready = summary?.ready_for_next_stage ?? false;
  const cov = a.analysis.coverage;
  const canRefine = answered >= 1;
  const engineLabel =
    ENGINES.find((e) => e.value === a.target.engine)?.label ?? a.target.engine;

  const blockingRemaining = a.questions_for_dba.filter(
    (q) => q.blocking && statusOf(q.id) === "pendiente",
  ).length;
  const pendingQuestions = a.questions_for_dba.filter(
    (q) => statusOf(q.id) === "pendiente",
  ).length;
  const mode = questionMode ?? (pendingQuestions > 0 ? "enfocado" : "lista");

  const ddlErrors = a.validation.errors.length;
  const ddlWarnings = a.validation.warnings.length;
  const piiColumns = a.tables.flatMap((t) =>
    t.columns.filter((c) => c.pii).map((c) => `${t.name}.${c.name}`),
  );
  const ambiguousColumns = a.tables.flatMap((t) =>
    t.columns.filter((c) => c.type_ambiguous).map((c) => `${t.name}.${c.name}`),
  );
  const catalogs = a.tables.filter((t) => t.kind === "catalog");
  const junctions = a.tables.filter((t) => t.kind === "junction");
  const entities = a.tables.filter((t) => t.kind === "entity");
  const notEnforced = a.rule_mappings.filter(
    (m) => m.enforcement !== "declarative",
  );

  // El diagrama ER debe estar renderizado antes de abrir el diálogo de impresión:
  // un PDF del modelo de datos sin su diagrama no sirve de nada.
  const printWhenDiagramReady = () =>
    !a.er_diagram.code ||
    document.querySelectorAll("#artifact-print-doc .mermaid-diagram svg").length >=
      1;

  const sheetQuestions = a.questions_for_dba.map(
    (q): SheetQuestion => ({
      id: q.id,
      question: q.question,
      reason: q.reason,
      blocking: q.blocking,
      linked_to_ref: q.linked_to_ref,
    }),
  );

  const questionControls = (id: string, onAnswered?: () => void) => (
    <DbaValidationControls
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

  const renderTables = (tables: DbTable[], query: string) => {
    const filtered = filterByQuery(query, tables, (t) => [
      t.name,
      t.description ?? "",
      ...t.columns.map((c) => c.name),
    ]);
    if (filtered.length === 0) return <EmptyHint>Sin tablas.</EmptyHint>;
    return (
      <DataList>
        {filtered.map((t) => (
          <TableBlock key={t.id} table={t} />
        ))}
      </DataList>
    );
  };

  // BD es hoy el último eslabón construido: con el semáforo en verde no hay
  // siguiente agente que ofrecer, así que el panel se cierra solo al terminar.
  const nextStepAction =
    puedeEditar && !ready && canRefine
      ? {
          label: "Regenerar modelo afinado",
          onClick: () => void doRefine(),
          hint: "Reinyecta tus respuestas y genera una versión afinada.",
        }
      : undefined;

  const sections: HubSection[] = [
    {
      id: "tablas",
      title: "Tablas",
      printTitle: "Modelo físico",
      icon: <Table2 />,
      count: a.tables.length,
      tone: "teal",
      pattern: "dots",
      stat: { value: a.tables.length, label: plural(a.tables.length, "tabla") },
      insight: (
        <>
          {a.metrics.columns_total} columnas · {a.metrics.constraints_total}{" "}
          restricciones · {a.metrics.indexes_total} índices
          {ambiguousColumns.length > 0 && (
            <>
              {" "}
              ·{" "}
              <span className="text-amber-700">
                {ambiguousColumns.length} con tipo por confirmar
              </span>
            </>
          )}
        </>
      ),
      tabs: [
        {
          id: "todas",
          label: "Todas",
          count: a.tables.length,
          render: ({ query }) => (
            <>
              {/* La franja de reconciliación va ARRIBA del listado: antes de
                  leer qué se propone, hay que saber cuánto de ello ya existe. */}
              {a.reconciliation && (
                <ReconciliationSummaryBar summary={a.reconciliation} />
              )}
              {renderTables(a.tables, query)}
            </>
          ),
        },
        {
          id: "entidades",
          label: "Entidades",
          count: entities.length,
          printSkip: true,
          render: ({ query }) => renderTables(entities, query),
        },
        {
          id: "catalogos",
          label: "Catálogos",
          count: catalogs.length,
          printSkip: true,
          render: ({ query }) => renderTables(catalogs, query),
        },
        {
          id: "puente",
          label: "Puente",
          count: junctions.length,
          printSkip: true,
          render: ({ query }) => renderTables(junctions, query),
        },
      ],
    },
    {
      id: "diagrama",
      title: "Diagrama ER",
      icon: <Network />,
      searchable: false,
      tone: "violet",
      pattern: "waves",
      stat: {
        value: a.tables.reduce((n, t) => n + t.foreign_keys.length, 0),
        label: "relaciones",
      },
      insight: "Entidad-relación con claves y cardinalidades.",
      render: () =>
        a.er_diagram.code ? (
          <MermaidDiagram code={a.er_diagram.code} />
        ) : (
          <EmptyHint>Sin diagrama.</EmptyHint>
        ),
    },
    {
      id: "ddl",
      title: "DDL",
      printTitle: "Scripts DDL",
      icon: <FileCode />,
      count: a.ddl_scripts.length,
      searchable: false,
      tone: "amber",
      pattern: "lines",
      stat: { value: engineLabel, label: "motor destino" },
      insight: a.validation.syntax_ok ? (
        <>Validado · {a.ddl_scripts.length} scripts listos para ejecutar</>
      ) : (
        <>DDL con errores: revisar antes de ejecutar</>
      ),
      urgent: ddlErrors > 0,
      urgentLabel: `${ddlErrors} error${ddlErrors === 1 ? "" : "es"}`,
      actions: (
        <div className="flex items-center gap-1.5 print:hidden">
          <span className="text-[11px] text-muted-foreground">Motor:</span>
          <select
            value={ddlEngine ?? a.target.engine}
            onChange={(e) => {
              const value = e.target.value as DbEngine;
              void cambiarMotorDdl(value === a.target.engine ? null : value);
            }}
            className="rounded-md border bg-background px-1.5 py-1 text-xs"
            aria-label="Motor del DDL"
          >
            {ENGINES.map((e) => (
              <option key={e.value} value={e.value}>
                {e.label}
                {e.value === a.target.engine ? " (del diseño)" : ""}
              </option>
            ))}
          </select>
        </div>
      ),
      render: ({ forPrint }) => {
        const scripts = a.ddl_scripts;
        const sqlActual =
          ddlSql ??
          scripts
            .slice()
            .sort((x, y) => x.order - y.order)
            .map((s) => s.sql)
            .join("\n");
        if (scripts.length === 0) return <EmptyHint>Sin DDL generado.</EmptyHint>;
        return (
          <div className="space-y-4">
            {!forPrint && (
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  className="gap-1.5"
                  onClick={() => {
                    void navigator.clipboard.writeText(sqlActual);
                    toast.success("DDL copiado al portapapeles");
                  }}
                >
                  <Copy className="h-3.5 w-3.5" />
                  Copiar todo
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="gap-1.5"
                  onClick={() =>
                    download(
                      sqlActual,
                      `modelo-${job.job_id}-${ddlEngine ?? a.target.engine}.sql`,
                      "application/sql",
                    )
                  }
                >
                  <Download className="h-3.5 w-3.5" />
                  Descargar .sql
                </Button>
                {ddlEngine && ddlEngine !== a.target.engine && (
                  <span className="text-xs text-muted-foreground">
                    Re-renderizado a {ENGINES.find((e) => e.value === ddlEngine)?.label}{" "}
                    sin volver a llamar al modelo. El diseño sigue registrado en{" "}
                    {engineLabel}.
                  </span>
                )}
                {ddlLoading && (
                  <span className="text-xs text-muted-foreground">Generando…</span>
                )}
              </div>
            )}
            {ddlEngine && ddlEngine !== a.target.engine ? (
              <ScriptBlock name={`DDL completo · ${ddlEngine}`} sql={sqlActual} />
            ) : (
              scripts
                .slice()
                .sort((x, y) => x.order - y.order)
                .map((s) => (
                  <ScriptBlock
                    key={s.id}
                    id={s.id}
                    name={s.name}
                    sql={s.sql}
                    destructive={s.kind === "rollback"}
                  />
                ))
            )}
          </div>
        );
      },
    },
    {
      id: "diccionario",
      title: "Diccionario",
      printTitle: "Diccionario de datos",
      icon: <BookOpen />,
      count: a.data_dictionary.length,
      tone: "sky",
      stat: {
        value: a.data_dictionary.length,
        label: plural(a.data_dictionary.length, "columna"),
      },
      insight: "Cada columna con su tipo, descripción, ejemplo y origen.",
      render: ({ query }) => {
        const rows = filterByQuery(query, a.data_dictionary, (d) => [
          d.table,
          d.column,
          d.type,
          d.description ?? "",
        ]);
        if (rows.length === 0) return <EmptyHint>Sin coincidencias.</EmptyHint>;
        return (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[42rem] text-sm">
              <thead>
                <tr className="border-b text-left text-xs text-muted-foreground">
                  <th className="py-1.5 pr-3 font-medium">Tabla</th>
                  <th className="py-1.5 pr-3 font-medium">Columna</th>
                  <th className="py-1.5 pr-3 font-medium">Tipo</th>
                  <th className="py-1.5 pr-3 font-medium">Nulo</th>
                  <th className="py-1.5 pr-3 font-medium">Clave</th>
                  <th className="py-1.5 pr-3 font-medium">Descripción</th>
                  <th className="py-1.5 font-medium">Ejemplo</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((d) => (
                  <tr key={d.id} className="border-b border-border/50 align-top">
                    <td className="py-1.5 pr-3">
                      <Mono>{d.table}</Mono>
                    </td>
                    <td className="py-1.5 pr-3">
                      <Mono>{d.column}</Mono>
                    </td>
                    <td className="py-1.5 pr-3 text-xs">{d.type}</td>
                    <td className="py-1.5 pr-3 text-xs">{d.nullable ? "sí" : "no"}</td>
                    <td className="py-1.5 pr-3 text-xs">{d.key}</td>
                    <td className="py-1.5 pr-3 text-xs text-muted-foreground">
                      {d.description ?? "—"}
                    </td>
                    <td className="py-1.5 text-xs text-muted-foreground">
                      {d.example ?? "—"}
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
      id: "semilla",
      title: "Datos semilla",
      icon: <Sprout />,
      count: a.seed_data.length,
      tone: "emerald",
      stat: {
        value: a.metrics.seed_rows_total,
        label: plural(a.metrics.seed_rows_total, "fila"),
      },
      insight:
        a.seed_data.length > 0
          ? "Valores citados en el EF, con su evidencia."
          : "Sin catálogos con valores enumerados en el EF.",
      render: ({ query }) => {
        const seeds = filterByQuery(query, a.seed_data, (s) => [
          s.table,
          s.reason ?? "",
        ]);
        if (seeds.length === 0)
          return (
            <EmptyHint>
              Ningún catálogo trajo valores citados en el EF. Los valores no se
              inventan: se preguntan al DBA.
            </EmptyHint>
          );
        return (
          <DataList>
            {seeds.map((s) => (
              <DataRow key={s.id} id={s.id}>
                <div className="space-y-2">
                  <p className="text-sm font-medium">
                    <Mono>{s.table}</Mono> · {s.rows.length}{" "}
                    {plural(s.rows.length, "fila")}
                  </p>
                  {s.reason && (
                    <p className="text-xs text-muted-foreground">{s.reason}</p>
                  )}
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="border-b text-left text-muted-foreground">
                          {s.columns.map((c) => (
                            <th key={c} className="py-1 pr-3 font-medium">
                              {c}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {s.rows.map((row, i) => (
                          <tr key={i} className="border-b border-border/50">
                            {s.columns.map((c) => (
                              <td key={c} className="py-1 pr-3">
                                {String(row[c] ?? "—")}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {s.evidence && (
                    <p className="border-l-2 border-emerald-300 pl-2 text-xs italic text-muted-foreground">
                      «{s.evidence}»
                    </p>
                  )}
                  <RefList label="Origen" refs={s.source_refs} />
                </div>
              </DataRow>
            ))}
          </DataList>
        );
      },
    },
    {
      id: "reglas",
      title: "Reglas del EF",
      printTitle: "Reglas y dónde se hacen cumplir",
      icon: <Gavel />,
      count: a.rule_mappings.length,
      tone: "indigo",
      stat: {
        value: `${a.rule_mappings.length - notEnforced.length}/${a.rule_mappings.length}`,
        label: "en el esquema",
      },
      insight:
        notEnforced.length > 0 ? (
          <>
            {notEnforced.length}{" "}
            {plural(notEnforced.length, "regla", "reglas")} quedan para la capa de
            aplicación
          </>
        ) : (
          "Todas las reglas se hacen cumplir en el esquema."
        ),
      render: ({ query }) => {
        const rows = filterByQuery(query, a.rule_mappings, (m) => [
          m.rule_ref,
          m.note ?? "",
        ]);
        if (rows.length === 0) return <EmptyHint>Sin reglas mapeadas.</EmptyHint>;
        return (
          <DataList>
            {rows.map((m) => (
              <DataRow key={m.id} id={m.id}>
                <div className="space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <RefChip refId={m.rule_ref} />
                    <Badge
                      variant="outline"
                      className={ENFORCEMENT_STYLE[m.enforcement]}
                    >
                      {ENFORCEMENT_LABEL[m.enforcement]}
                    </Badge>
                    {m.constraint_ref && <RefChip refId={m.constraint_ref} />}
                  </div>
                  {m.note && (
                    <p className="text-xs text-muted-foreground">{m.note}</p>
                  )}
                </div>
              </DataRow>
            ))}
          </DataList>
        );
      },
    },
    {
      id: "decisiones",
      title: "Decisiones",
      printTitle: "Decisiones de diseño de datos",
      icon: <Layers />,
      count: a.design_decisions.length,
      tone: "blue",
      stat: {
        value: a.design_decisions.length,
        label: plural(a.design_decisions.length, "decisión", "decisiones"),
      },
      insight: "Claves, normalización y catálogos, con sus alternativas.",
      render: ({ query }) => {
        const rows = filterByQuery(query, a.design_decisions, (d) => [
          d.title,
          d.decision,
          d.rationale,
        ]);
        if (rows.length === 0) return <EmptyHint>Sin decisiones.</EmptyHint>;
        return (
          <DataList>
            {rows.map((d) => (
              <DataRow key={d.id} id={d.id}>
                <div className="space-y-1.5">
                  <p className="text-sm font-medium">{d.title}</p>
                  <p className="text-sm">{d.decision}</p>
                  <p className="text-xs text-muted-foreground">{d.rationale}</p>
                  {d.alternatives_considered.length > 0 && (
                    <p className="text-xs text-muted-foreground">
                      Alternativas: {d.alternatives_considered.join(" · ")}
                    </p>
                  )}
                  {d.consequences.length > 0 && (
                    <ul className="ml-4 list-disc text-xs text-muted-foreground">
                      {d.consequences.map((c) => (
                        <li key={c}>{c}</li>
                      ))}
                    </ul>
                  )}
                  <div className="flex flex-wrap gap-1">
                    <RefList label="Tablas" refs={d.table_refs} />
                    <RefList label="Origen" refs={d.source_refs} />
                  </div>
                </div>
              </DataRow>
            ))}
          </DataList>
        );
      },
    },
    {
      id: "validacion",
      title: "Validación del DDL",
      icon: <ShieldCheck />,
      searchable: false,
      tone: ddlErrors > 0 ? "rose" : "emerald",
      stat: {
        value: ddlErrors === 0 ? "OK" : ddlErrors,
        label: ddlErrors === 0 ? "sin errores" : plural(ddlErrors, "error", "errores"),
      },
      insight: (
        <>
          {a.validation.executed
            ? "Ejecutado contra el motor."
            : `Comprobado con ${a.validation.validator ?? "validación estructural"} (sin ejecutar).`}
          {ddlWarnings > 0 && ` ${ddlWarnings} aviso(s).`}
        </>
      ),
      urgent: ddlErrors > 0,
      urgentLabel: "DDL inválido",
      render: () => (
        <div className="space-y-4">
          <div className="rounded-lg border bg-muted/20 p-3 text-xs text-muted-foreground">
            {a.validation.executed
              ? "El DDL se ejecutó contra un motor real."
              : "El DDL se comprobó de forma estructural y se parseó en el dialecto destino. No se ejecutó contra un motor: eso es una certificación aparte."}
          </div>
          <div>
            <GroupLabel>Comprobaciones</GroupLabel>
            <ul className="mt-1 grid gap-1 sm:grid-cols-2">
              {Object.entries(a.validation.checks).map(([name, ok]) => (
                <li key={name} className="flex items-center gap-2 text-xs">
                  {ok ? (
                    <Check className="h-3.5 w-3.5 text-emerald-600" />
                  ) : (
                    <AlertTriangle className="h-3.5 w-3.5 text-red-600" />
                  )}
                  <Mono>{name}</Mono>
                </li>
              ))}
            </ul>
          </div>
          {a.validation.errors.length > 0 && (
            <div>
              <GroupLabel>Errores</GroupLabel>
              <DataList>
                {a.validation.errors.map((e, i) => (
                  <DataRow key={`${e.code}-${i}`} id={e.code}>
                    <p className="text-sm text-red-700">{e.message}</p>
                    {e.ref && <RefChip refId={e.ref} />}
                  </DataRow>
                ))}
              </DataList>
            </div>
          )}
          {a.validation.warnings.length > 0 && (
            <div>
              <GroupLabel>Avisos</GroupLabel>
              <DataList>
                {a.validation.warnings.map((w, i) => (
                  <DataRow key={`${w.code}-${i}`} id={w.code}>
                    <p className="text-sm text-amber-700">{w.message}</p>
                    {w.ref && <RefChip refId={w.ref} />}
                  </DataRow>
                ))}
              </DataList>
            </div>
          )}
        </div>
      ),
    },
    {
      id: "analisis",
      title: "Análisis",
      icon: <AlertTriangle />,
      count: a.analysis.risks.length + a.analysis.observations.length,
      tone: "rose",
      stat: {
        value: `${Math.round(a.metrics.coverage * 100)}%`,
        label: "cobertura del EF",
      },
      insight: (
        <>
          {a.analysis.risks.length} {plural(a.analysis.risks.length, "riesgo")} ·{" "}
          {piiColumns.length} con datos personales
        </>
      ),
      tabs: [
        {
          id: "riesgos",
          label: "Riesgos",
          count: a.analysis.risks.length,
          render: ({ query }) => {
            const rows = filterByQuery(query, a.analysis.risks, (r) => [
              r.description,
              r.mitigation ?? "",
            ]);
            if (rows.length === 0) return <EmptyHint>Sin riesgos.</EmptyHint>;
            return (
              <DataList>
                {rows.map((r) => (
                  <DataRow key={r.id} id={r.id}>
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <Badge
                          variant="outline"
                          className={SEVERITY_STYLE[r.severity]}
                        >
                          {r.severity}
                        </Badge>
                        {r.source_ref && <RefChip refId={r.source_ref} />}
                      </div>
                      <p className="text-sm">{r.description}</p>
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
          render: () => (
            <div className="space-y-2 text-sm">
              <p>
                Entidades: {cov.entities_mapped}/{cov.entities_total} · Campos:{" "}
                {cov.fields_mapped}/{cov.fields_total}
              </p>
              <p>
                Reglas en el esquema: {cov.rules_enforced}/{cov.rules_total} ·
                Validaciones: {cov.validations_enforced}/{cov.validations_total}
              </p>
              <div className="space-y-1 text-xs text-muted-foreground">
                <UncoveredLine
                  label="Entidades"
                  refs={cov.uncovered_entity_refs}
                />
                <UncoveredLine label="Campos" refs={cov.unmapped_field_refs} />
                <UncoveredLine
                  label="Validaciones"
                  refs={cov.unenforced_validation_refs}
                />
                <UncoveredLine label="Reglas" refs={cov.unenforced_rule_refs} />
              </div>
              {piiColumns.length > 0 && (
                <p className="text-xs text-muted-foreground">
                  Datos personales detectados: {piiColumns.join(", ")}.
                </p>
              )}
            </div>
          ),
        },
        {
          id: "observaciones",
          label: "Observaciones",
          count: a.analysis.observations.length,
          render: ({ query }) => {
            const rows = filterByQuery(query, a.analysis.observations, (o) => [
              o.description,
              o.reason ?? "",
            ]);
            if (rows.length === 0) return <EmptyHint>Sin observaciones.</EmptyHint>;
            return (
              <DataList>
                {rows.map((o) => (
                  <DataRow key={o.id} id={o.id}>
                    <p className="text-sm">{o.description}</p>
                    {o.reason && (
                      <p className="text-xs text-muted-foreground">{o.reason}</p>
                    )}
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
      title: "Preguntas al DBA",
      icon: <MessagesSquare />,
      count: a.questions_for_dba.length,
      tone: "amber",
      stat: {
        value: pendingQuestions,
        label: pendingQuestions === 1 ? "pendiente" : "pendientes",
      },
      insight:
        blockingRemaining > 0 ? (
          <>{blockingRemaining} bloquean el paso al Agente API</>
        ) : (
          "Ninguna pregunta bloquea el avance."
        ),
      urgent: blockingRemaining > 0,
      urgentLabel: `${blockingRemaining} bloqueante${blockingRemaining === 1 ? "" : "s"}`,
      actions:
        a.questions_for_dba.length > 0 ? (
          <Segmented
            value={mode}
            onChange={(v) => setQuestionMode(v)}
            options={[
              { value: "enfocado", label: "Una a una" },
              { value: "lista", label: "Lista" },
            ]}
          />
        ) : undefined,
      render: ({ query, forPrint }) => {
        if (a.questions_for_dba.length === 0)
          return <EmptyHint>Sin preguntas: el modelo está completo.</EmptyHint>;

        if (mode === "enfocado" && !forPrint) {
          return (
            <FocusedQuestionFlow
              questions={sheetQuestions}
              statusOf={statusOf}
              renderControls={(q, onAnswered) =>
                questionControls(q.id, onAnswered)
              }
              ready={ready}
              readyLabel="Listo para el Agente API"
              nextAction={nextStepAction}
              onClose={hub.close}
            />
          );
        }

        const rows = filterByQuery(query, a.questions_for_dba, (q) => [
          q.question,
          q.reason,
        ]);
        if (rows.length === 0) return <EmptyHint>Sin coincidencias.</EmptyHint>;
        return (
          <div className="space-y-3">
            {!forPrint && <ValidationHint />}
                        {rows.map((q) => (
              <div key={q.id} className="rounded-lg border p-3">
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
          kind="Modelo de Datos"
          title={`Modelo físico · ${engineLabel}`}
          subtitle="Tablas, claves, índices, restricciones, DDL ejecutable, datos semilla, diccionario y diagrama entidad-relación."
          version="1.0.0"
          stats={[
            { label: "tablas", value: String(a.tables.length) },
            { label: "columnas", value: String(a.metrics.columns_total) },
            { label: "índices", value: String(a.metrics.indexes_total) },
            {
              label: "cobertura",
              value: `${Math.round(a.metrics.coverage * 100)}%`,
            },
          ]}
        />
        <PrintFooter title="Modelo de Datos" />

        {/* Barra superior de afinamiento + semáforo */}
        <div className="sticky top-0 z-10 border-b bg-background/95 px-6 py-4 backdrop-blur print:hidden">
          <div className={HUB_WIDTH}>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-2 text-sm">
              <span className="font-heading font-semibold">
                Modelo de datos v1.0.0
              </span>
              <Badge variant="outline">
                {job.parent_job_id ? "v2 · afinamiento" : "v1 · original"}
              </Badge>
              <Badge variant="outline" className="gap-1">
                <Database className="h-3 w-3" />
                {engineLabel}
                {a.target.engine_version ? ` ${a.target.engine_version}` : ""}
              </Badge>
              {!a.target.engine_decided && (
                <Badge
                  variant="outline"
                  className="border-amber-300 bg-amber-50 text-amber-700"
                  title="La arquitectura no decidió motor: se usó el estándar de la casa"
                >
                  motor por confirmar
                </Badge>
              )}
              {job.input_job_id && (
                <Link
                  href={`/agents/arquitectura/jobs/${job.input_job_id}`}
                  className="text-xs text-muted-foreground underline-offset-2 hover:text-primary hover:underline"
                >
                  arquitectura (<Mono>{job.input_job_id}</Mono>)
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
                {ready ? "Listo para el Agente API" : "Pendiente de afinamiento"}
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
                  {puedeEditar && a.questions_for_dba.length > 0 && (
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
                      // Espera al SVG del diagrama ER: un PDF del modelo de datos
                      // sin su diagrama no sirve.
                      onClick={() => printNow(printWhenDiagramReady)}
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
                          a.ddl_scripts
                            .slice()
                            .sort((x, y) => x.order - y.order)
                            .map((s) => s.sql)
                            .join("\n"),
                          `modelo-${job.job_id}-${a.target.engine}.sql`,
                          "application/sql",
                        )
                      }
                    >
                      <FileCode className="h-3.5 w-3.5" />
                      DDL
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      className="gap-1.5"
                      onClick={() =>
                        download(
                          JSON.stringify(a, null, 2),
                          `bd-artifact-${job.job_id}.json`,
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
                              Regenerar modelo afinado
                            </Button>
                          }
                        />
                        <DialogContent>
                          <DialogHeader>
                            <DialogTitle>Regenerar modelo afinado</DialogTitle>
                            <DialogDescription>
                              Se creará un modelo hijo reinyectando las respuestas
                              del DBA y se ejecutará el modelo real.
                            </DialogDescription>
                          </DialogHeader>
                          <div className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800">
                            Costo estimado: ~${a.metrics.cost.toFixed(4)} (similar
                            al modelo anterior). Esta acción consume tokens de la
                            API.
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
                <Stat icon={<Table2 />} value={a.tables.length} label="tablas" />
                <Stat
                  icon={<Boxes />}
                  value={a.metrics.columns_total}
                  label="columnas"
                />
                <Stat
                  icon={<KeyRound />}
                  value={a.metrics.constraints_total}
                  label="restricciones"
                />
                <Stat
                  icon={<ListChecks />}
                  value={a.metrics.indexes_total}
                  label="índices"
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
                  label="costo estimado"
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

        <ArtifactPanel hub={hub} sections={sections} module="bd" />
        <ArtifactPrintDoc sections={sections} active={printMode} />
      </div>
    </ArtifactNavProvider>
  );
}

// --- subcomponentes ----------------------------------------------------------

/** Una tabla del modelo: columnas, clave primaria, FK, restricciones e índices. */
function TableBlock({ table }: { table: DbTable }) {
  return (
    <DataRow id={table.id}>
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-heading text-sm font-semibold">
            <Mono>{table.name}</Mono>
          </span>
          <Badge variant="outline">{KIND_LABEL[table.kind] ?? table.kind}</Badge>
          {table.entity_ref && <RefChip refId={table.entity_ref} />}
          <ConfidenceBadge value={table.confidence ?? undefined} />
          <ReconciliationBadge reconciliation={table.reconciliation} />
          {table.normalization.denormalized && (
            <Badge
              variant="outline"
              className="border-amber-300 bg-amber-50 text-amber-700"
            >
              desnormalizada
            </Badge>
          )}
        </div>
        {table.reconciliation && (
          <ReconciliationDetail reconciliation={table.reconciliation} />
        )}
        {table.description && (
          <p className="text-xs text-muted-foreground">{table.description}</p>
        )}

        <div className="overflow-x-auto">
          <table className="w-full min-w-[34rem] text-xs">
            <thead>
              <tr className="border-b text-left text-muted-foreground">
                <th className="py-1 pr-3 font-medium">Columna</th>
                <th className="py-1 pr-3 font-medium">Tipo</th>
                <th className="py-1 pr-3 font-medium">Nulo</th>
                <th className="py-1 pr-3 font-medium">Clave</th>
                <th className="py-1 font-medium">Origen</th>
              </tr>
            </thead>
            <tbody>
              {table.columns.map((c) => (
                <ColumnRow key={c.id} table={table} column={c} />
              ))}
            </tbody>
          </table>
        </div>

        {table.primary_key && (
          <p className="text-xs text-muted-foreground">
            <b>PK</b> <Mono>{table.primary_key.name}</Mono> (
            {table.primary_key.columns.join(", ")}) · {table.primary_key.strategy}
            {table.primary_key.rationale ? ` — ${table.primary_key.rationale}` : ""}
          </p>
        )}

        {table.foreign_keys.length > 0 && (
          <div className="space-y-1">
            <GroupLabel>Claves foráneas</GroupLabel>
            {table.foreign_keys.map((fk) => (
              <p key={fk.id} className="text-xs text-muted-foreground">
                <IdTag id={fk.id} /> <Mono>{fk.columns.join(", ")}</Mono> →{" "}
                <Mono>
                  {fk.references_table}({fk.references_columns.join(", ")})
                </Mono>{" "}
                · ON DELETE {fk.on_delete}
                {fk.rationale ? ` — ${fk.rationale}` : ""}
              </p>
            ))}
          </div>
        )}

        {(table.unique_constraints.length > 0 ||
          table.check_constraints.length > 0) && (
          <div className="space-y-1">
            <GroupLabel>Restricciones</GroupLabel>
            {table.unique_constraints.map((uq) => (
              <p key={uq.id} className="text-xs text-muted-foreground">
                <IdTag id={uq.id} /> UNIQUE ({uq.columns.join(", ")}){" "}
                <RefList label="" refs={uq.source_refs} />
              </p>
            ))}
            {table.check_constraints.map((ck) => (
              <p key={ck.id} className="text-xs text-muted-foreground">
                <IdTag id={ck.id} /> CHECK (<Mono>{ck.expression}</Mono>){" "}
                <RefList label="" refs={ck.source_refs} />
              </p>
            ))}
          </div>
        )}

        {table.indexes.length > 0 && (
          <div className="space-y-1">
            <GroupLabel>Índices</GroupLabel>
            {table.indexes.map((idx) => (
              <p key={idx.id} className="text-xs text-muted-foreground">
                <IdTag id={idx.id} /> <Mono>{idx.name}</Mono> (
                {idx.columns.join(", ")}) — {idx.rationale}
              </p>
            ))}
          </div>
        )}
      </div>
    </DataRow>
  );
}

function ColumnRow({ table, column }: { table: DbTable; column: DbColumn }) {
  const isFk = table.foreign_keys.some((fk) => fk.columns.includes(column.name));
  const marks = [
    column.is_primary_key ? "PK" : null,
    isFk ? "FK" : null,
    table.unique_constraints.some((uq) => uq.columns.includes(column.name))
      ? "UQ"
      : null,
  ].filter(Boolean);

  return (
    <tr className="border-b border-border/50 align-top">
      <td className="py-1 pr-3">
        <Mono>{column.name}</Mono>
        {column.pii && (
          <span
            className="ml-1 text-[10px] text-amber-700"
            title="Candidata a dato personal"
          >
            PII
          </span>
        )}
      </td>
      <td className="py-1 pr-3">
        {column.type ?? column.logical_type}
        {column.type_ambiguous && (
          <span
            className="ml-1 text-[10px] text-amber-700"
            title="El EF no permitía deducir el tipo: hay una pregunta al DBA"
          >
            ?
          </span>
        )}
      </td>
      <td className="py-1 pr-3">{column.nullable ? "sí" : "no"}</td>
      <td className="py-1 pr-3">{marks.join(",") || "—"}</td>
      <td className="py-1">
        {column.field_ref ? <RefChip refId={column.field_ref} /> : "derivada"}
      </td>
    </tr>
  );
}

/** Bloque de un script DDL con su cabecera y su SQL monoespaciado. */
function ScriptBlock({
  id,
  name,
  sql,
  destructive = false,
}: {
  id?: string;
  name: string;
  sql: string;
  destructive?: boolean;
}) {
  return (
    <div
      className={cn(
        "rounded-lg border",
        destructive && "border-red-300 bg-red-50/40",
      )}
    >
      <div className="flex items-center gap-2 border-b px-3 py-1.5">
        {id && <IdTag id={id} />}
        <span className="font-mono text-xs font-medium">{name}</span>
        {destructive && (
          <Badge
            variant="outline"
            className="border-red-300 bg-red-50 text-red-700"
          >
            destructivo
          </Badge>
        )}
        <button
          type="button"
          className="ml-auto text-[11px] text-muted-foreground hover:text-foreground print:hidden"
          onClick={() => {
            void navigator.clipboard.writeText(sql);
            toast.success(`${name} copiado`);
          }}
        >
          Copiar
        </button>
      </div>
      <pre className="overflow-x-auto p-3 font-mono text-[11px] leading-relaxed">
        {sql}
      </pre>
    </div>
  );
}

function RefList({ label, refs }: { label: string; refs: string[] }) {
  if (!refs || refs.length === 0) return null;
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      {label ? `${label}: ` : null}
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

/** Conmutador segmentado compacto (modo de preguntas). */
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
