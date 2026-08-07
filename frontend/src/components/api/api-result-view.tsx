"use client";

// CENTRO DE COMANDO del contrato de API. Mismo patrón que EF, Scrum,
// Arquitectura y BD: cabecera + grid de tarjetas-sección, contenido en el panel
// lateral universal y PDF como documento lineal.
//
// Lo propio de esta vista son dos cosas. La **matriz de autorización**, que es su
// visual insignia: se lee de un vistazo quién puede llamar qué, y —más
// importante— dónde no lo puede nadie. Y el **documento OpenAPI**, que no es
// documentación sino un entregable de máquina: se copia, se descarga y se puede
// pedir en JSON sin volver a llamar al modelo.
//
// El YAML crudo lleva `printSkip`: un informe con mil líneas de YAML no lo lee
// nadie y duplica lo que las tablas de endpoints cuentan mejor. El PDF imprime la
// ficha del documento y dice dónde descargarlo.

import {
  AlertTriangle,
  Braces,
  Coins,
  Copy,
  DollarSign,
  Download,
  Eye,
  FileJson,
  Gavel,
  KeyRound,
  Layers,
  ListChecks,
  MessagesSquare,
  Plug,
  Printer,
  Route,
  ShieldCheck,
  Target,
  TriangleAlert,
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
  AuthorizationMatrix,
  MethodChip,
} from "@/components/api/authorization-matrix";
import { TechLeadValidationControls } from "@/components/api/validation-controls";
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
import { API_REF_ROUTES } from "@/lib/api-refs";
import { apisApi } from "@/lib/api/apis";
import { ApiError } from "@/lib/api/client";
import { makeRefResolver } from "@/lib/artifact-refs";
import { filterByQuery, plural } from "@/lib/artifact-search";
import { useAuth } from "@/lib/auth/auth-context";
import type { RiskSeverity } from "@/lib/types/arquitectura";
import type {
  ApiArtifact,
  ApiDataSchema,
  ApiEndpoint,
  ApiJobDetail,
  ApiResource,
  ApiValidationSummary,
} from "@/lib/types/api";
import type { QuestionStatus } from "@/lib/types/ef";
import { useArtifactHub } from "@/lib/use-artifact-hub";
import { useCelebrateOnTrue } from "@/lib/use-celebrate-on-true";
import { usePrintExpand } from "@/lib/use-print-expand";
import { cn } from "@/lib/utils";

const SEVERITY_STYLE: Record<RiskSeverity, string> = {
  alta: "border-red-300 bg-red-50 text-red-700",
  media: "border-amber-300 bg-amber-50 text-amber-700",
  baja: "border-slate-300 bg-slate-50 text-slate-600",
};

const EXPOSURE_LABEL: Record<string, string> = {
  crud: "CRUD completo",
  read_only: "solo lectura",
  nested_only: "anidado",
  none: "sin exponer",
};

const SCHEMA_KIND_LABEL: Record<string, string> = {
  create: "alta",
  update: "actualización",
  read: "detalle",
  list_item: "resumen",
  action_input: "entrada de acción",
  error: "error",
  envelope: "envoltorio",
};

const ENFORCEMENT_LABEL: Record<string, string> = {
  endpoint: "en la operación",
  schema: "en el contrato de datos",
  authorization: "en el control de acceso",
  database: "en el modelo de datos",
  not_applicable: "fuera de la API",
};

const ENFORCEMENT_STYLE: Record<string, string> = {
  endpoint: "border-sky-300 bg-sky-50 text-sky-700",
  schema: "border-emerald-300 bg-emerald-50 text-emerald-700",
  authorization: "border-violet-300 bg-violet-50 text-violet-700",
  database: "border-slate-300 bg-slate-50 text-slate-600",
  not_applicable: "border-amber-300 bg-amber-50 text-amber-700",
};

const SECTION_IDS = [
  "contrato",
  "recursos",
  "endpoints",
  "autorizacion",
  "esquemas",
  "errores",
  "reglas",
  "openapi",
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

export function ApiResultView({ job }: { job: ApiJobDetail }) {
  const router = useRouter();
  const [artifact, setArtifact] = useState<ApiArtifact | null>(null);
  const [summary, setSummary] = useState<ApiValidationSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refining, setRefining] = useState(false);
  const [questionMode, setQuestionMode] = useState<"lista" | "enfocado" | null>(
    null,
  );

  const hub = useArtifactHub(SECTION_IDS);
  const { printMode, printNow } = usePrintExpand();
  // Modo lectura: con acceso de solo lectura al módulo «api» se muestra todo el
  // contenido pero se retiran las acciones de escritura. El backend las
  // rechazaría con 403.
  const { can } = useAuth();
  const puedeEditar = can("api", "full");
  const celebrate = useCelebrateOnTrue(
    summary?.ready_for_next_stage ?? false,
    summary != null,
  );

  const loadAll = useCallback(() => {
    Promise.all([
      apisApi.getArtifact(job.job_id),
      apisApi.getValidationSummary(job.job_id),
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
            : "No se pudo cargar la especificación.",
        ),
      )
      .finally(() => setLoading(false));
  }, [job.job_id]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const reloadSummary =
    useCallback(async (): Promise<ApiValidationSummary | null> => {
      try {
        const s = await apisApi.getValidationSummary(job.job_id);
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

  const resolveRef = useMemo(() => makeRefResolver(API_REF_ROUTES), []);
  const canNavigateToRef = useCallback(
    (refId: string) => resolveRef(refId) !== null,
    [resolveRef],
  );
  const navigateToRef = useCallback(
    (refId: string) => {
      const target = resolveRef(refId);
      if (!target) {
        toast.info(
          `${refId} pertenece a las fuentes (EF, arquitectura o modelo de datos), no a este contrato.`,
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
      const child = await apisApi.refine(job.job_id);
      toast.success("Especificación afinada en curso");
      router.push(`/agents/api/jobs/${child.job_id}`);
    } catch (err) {
      toast.error("No se pudo regenerar", {
        description: err instanceof ApiError ? err.message : undefined,
      });
    } finally {
      setRefining(false);
    }
  }, [job.job_id, router]);

  const descargarJson = useCallback(async () => {
    try {
      const data = await apisApi.getOpenApi(job.job_id, "json");
      download(
        data.content,
        `openapi-${job.job_id}.json`,
        "application/json",
      );
    } catch (err) {
      toast.error("No se pudo obtener el documento en JSON", {
        description: err instanceof ApiError ? err.message : undefined,
      });
    }
  }, [job.job_id]);

  if (loading) return <ArtifactSkeleton />;
  if (error || !artifact) {
    return (
      <div className="p-6 text-sm text-red-600">
        {error ?? "No se pudo cargar la especificación."}
      </div>
    );
  }

  const a = artifact;
  const ready = summary?.ready_for_next_stage ?? false;
  const blockingRemaining = summary?.blocking_pending.length ?? 0;
  const canRefine = answered > 0;

  const esquemaDe = (ref?: string | null) =>
    ref ? a.schemas.find((s) => s.id === ref) : undefined;

  const endpointsPorRecurso = a.resources
    .map((recurso) => ({
      recurso,
      endpoints: a.endpoints.filter((e) => e.resource_ref === recurso.id),
    }))
    .filter((g) => g.endpoints.length > 0);

  const sinAutorizar = a.endpoints.filter(
    (e) =>
      !a.authorization_matrix.some(
        (r) => r.endpoint_ref === e.id && r.effect === "allow",
      ),
  );
  const ambiguos = a.authorization_matrix.filter((r) => r.ambiguous);
  const escritura = a.endpoints.filter((e) => e.method !== "GET");
  const sinExponer = a.resources.filter((r) => r.exposure !== "crud");
  const reglasSinDestino = a.rule_mappings.filter(
    (m) =>
      m.enforcement === "not_applicable" ||
      (m.bd_enforcement === "application" &&
        m.endpoint_refs.length === 0 &&
        m.schema_field_refs.length === 0 &&
        m.auth_rule_refs.length === 0),
  );
  const camposTotales = a.schemas.reduce((n, s) => n + s.fields.length, 0);

  const questions: SheetQuestion[] = a.questions_for_tech_lead.map((q) => ({
    id: q.id,
    question: q.question,
    reason: q.reason,
    blocking: q.blocking,
    linked_to_ref: q.linked_to_ref,
  }));

  const renderEndpoints = (lista: ApiEndpoint[], query: string) => {
    const grupos = endpointsPorRecurso
      .map(({ recurso, endpoints }) => ({
        recurso,
        endpoints: filterByQuery(query, endpoints.filter((e) => lista.includes(e)), (e) => [e.operation_id, e.path, e.purpose, e.method],
        ),
      }))
      .filter((g) => g.endpoints.length > 0);

    if (grupos.length === 0) return <EmptyHint>Sin coincidencias.</EmptyHint>;
    return (
      <div className="space-y-4">
        {grupos.map(({ recurso, endpoints }) => (
          <div key={recurso.id} className="space-y-1.5">
            <GroupLabel>
              {recurso.display_name || recurso.name} ({endpoints.length})
            </GroupLabel>
            <DataList>
              {endpoints.map((e) => (
                <EndpointBlock
                  key={e.id}
                  endpoint={e}
                  requestSchema={esquemaDe(e.request_schema_ref)}
                  responseSchema={esquemaDe(e.response_schema_ref)}
                  sinPermiso={sinAutorizar.includes(e)}
                />
              ))}
            </DataList>
          </div>
        ))}
      </div>
    );
  };

  // Con el semáforo en rojo, el paso siguiente es regenerar; en verde, el
  // contrato ya habilita a Backend y Frontend y el panel se cierra solo.
  const nextStepAction =
    puedeEditar && !ready && canRefine
      ? {
          label: "Regenerar contrato afinado",
          onClick: () => void doRefine(),
          hint: "Reinyecta tus respuestas y genera una versión afinada.",
        }
      : undefined;

  const sections: HubSection[] = [
    {
      id: "endpoints",
      title: "Endpoints",
      printTitle: "Catálogo de operaciones",
      icon: <Route />,
      count: a.endpoints.length,
      tone: "sky",
      pattern: "lines",
      stat: {
        value: a.endpoints.length,
        label: plural(a.endpoints.length, "operación", "operaciones"),
      },
      insight: (
        <>
          {endpointsPorRecurso.length} recursos · {escritura.length} de escritura
          {sinAutorizar.length > 0 && (
            <>
              {" "}
              ·{" "}
              <span className="text-red-700">
                {sinAutorizar.length} sin autorizar
              </span>
            </>
          )}
        </>
      ),
      urgent: sinAutorizar.length > 0,
      urgentLabel: `${sinAutorizar.length} sin autorizar`,
      tabs: [
        {
          id: "todas",
          label: "Todas",
          count: a.endpoints.length,
          render: ({ query }) => renderEndpoints(a.endpoints, query),
        },
        {
          id: "escritura",
          label: "Escritura",
          count: escritura.length,
          printSkip: true,
          render: ({ query }) => renderEndpoints(escritura, query),
        },
        {
          id: "sin-autorizar",
          label: "Sin autorizar",
          count: sinAutorizar.length,
          printSkip: true,
          render: ({ query }) => renderEndpoints(sinAutorizar, query),
        },
      ],
    },
    {
      id: "autorizacion",
      title: "Autorización",
      printTitle: "Matriz de autorización",
      icon: <ShieldCheck />,
      count: a.authorization_matrix.length,
      searchable: false,
      tone: "violet",
      pattern: "dots",
      stat: {
        value: a.analysis.coverage.actors_total,
        label: plural(a.analysis.coverage.actors_total, "actor", "actores"),
      },
      insight:
        ambiguos.length > 0 ? (
          <span className="text-amber-700">
            {ambiguos.length} alcance(s) sin resolver
          </span>
        ) : (
          <>
            {a.authorization_matrix.length} reglas · quién puede llamar qué
          </>
        ),
      urgent: ambiguos.length > 0 || sinAutorizar.length > 0,
      urgentLabel:
        ambiguos.length > 0
          ? `${ambiguos.length} sin resolver`
          : `${sinAutorizar.length} sin permiso`,
      render: ({ refId }) => (
        <AuthorizationMatrix
          endpoints={a.endpoints}
          rules={a.authorization_matrix}
          highlightId={refId}
        />
      ),
    },
    {
      id: "recursos",
      title: "Recursos",
      icon: <Layers />,
      count: a.resources.length,
      tone: "teal",
      pattern: "dots",
      stat: { value: a.resources.length, label: plural(a.resources.length, "recurso") },
      insight: (
        <>
          {a.resources.length - sinExponer.length} con CRUD ·{" "}
          {sinExponer.length} con exposición acotada
        </>
      ),
      render: ({ query }) => {
        const items = filterByQuery(query, a.resources, (r) => [
          r.name,
          r.display_name ?? "",
          r.description ?? "",
        ]);
        if (items.length === 0) return <EmptyHint>Sin coincidencias.</EmptyHint>;
        return (
          <DataList>
            {items.map((r) => (
              <ResourceBlock
                key={r.id}
                resource={r}
                endpoints={a.endpoints.filter((e) => e.resource_ref === r.id)}
              />
            ))}
          </DataList>
        );
      },
    },
    {
      id: "esquemas",
      title: "Esquemas",
      printTitle: "Contratos de datos",
      icon: <Braces />,
      count: a.schemas.length,
      tone: "emerald",
      pattern: "dots",
      stat: { value: camposTotales, label: "campos" },
      insight: (
        <>
          {a.schemas.length} esquemas · todo campo nace de una columna del modelo
        </>
      ),
      render: ({ query }) => {
        const items = filterByQuery(query, a.schemas, (s) => [
          s.name,
          s.description ?? "",
          ...s.fields.map((f) => f.name),
        ]);
        if (items.length === 0) return <EmptyHint>Sin coincidencias.</EmptyHint>;
        return (
          <DataList>
            {items.map((s) => (
              <SchemaBlock key={s.id} schema={s} />
            ))}
          </DataList>
        );
      },
    },
    {
      id: "reglas",
      title: "Reglas del EF",
      printTitle: "Trazabilidad de reglas",
      icon: <Gavel />,
      count: a.rule_mappings.length,
      tone: "amber",
      pattern: "lines",
      stat: {
        value: `${a.analysis.coverage.rules_enforced}/${a.analysis.coverage.rules_total}`,
        label: "con destino",
      },
      insight:
        reglasSinDestino.length > 0 ? (
          <span className="text-amber-700">
            {reglasSinDestino.length} sin destino en la API
          </span>
        ) : (
          <>Cada regla del EF, con dónde se hace cumplir</>
        ),
      urgent: reglasSinDestino.length > 0,
      urgentLabel: `${reglasSinDestino.length} sin destino`,
      render: ({ query }) => {
        const items = filterByQuery(query, a.rule_mappings, (m) => [
          m.rule_ref,
          m.note ?? "",
          m.enforcement,
        ]);
        if (items.length === 0) return <EmptyHint>Sin coincidencias.</EmptyHint>;
        return (
          <DataList>
            {items.map((m) => (
              <DataRow key={m.id} id={m.id}>
                <div className="space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <IdTag id={m.id} />
                    <RefChip refId={m.rule_ref} />
                    <Badge
                      variant="outline"
                      className={ENFORCEMENT_STYLE[m.enforcement]}
                    >
                      {ENFORCEMENT_LABEL[m.enforcement] ?? m.enforcement}
                    </Badge>
                    {m.bd_enforcement && (
                      <span
                        className="text-[11px] text-muted-foreground"
                        title="Lo que decidió el Agente BD sobre la misma regla"
                      >
                        BD: {m.bd_enforcement}
                      </span>
                    )}
                  </div>
                  {m.note && (
                    <p className="text-xs text-muted-foreground">{m.note}</p>
                  )}
                  <div className="flex flex-wrap items-center gap-1">
                    {[
                      ...m.endpoint_refs,
                      ...m.schema_field_refs,
                      ...m.auth_rule_refs,
                    ].map((ref) => (
                      <RefChip key={ref} refId={ref} />
                    ))}
                  </div>
                </div>
              </DataRow>
            ))}
          </DataList>
        );
      },
    },
    {
      id: "errores",
      title: "Errores",
      printTitle: "Catálogo de errores",
      icon: <TriangleAlert />,
      count: a.error_catalog.length,
      tone: "rose",
      pattern: "dots",
      stat: { value: a.error_catalog.length, label: "códigos" },
      insight: "Solo los que algún endpoint puede devolver.",
      render: ({ query }) => {
        const items = filterByQuery(query, a.error_catalog, (e) => [
          e.code,
          e.message,
          String(e.status),
        ]);
        if (items.length === 0) return <EmptyHint>Sin coincidencias.</EmptyHint>;
        return (
          <DataList>
            {items.map((e) => (
              <DataRow key={e.id} id={e.id}>
                <div className="space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <IdTag id={e.id} />
                    <Badge variant="outline">{e.status}</Badge>
                    <Mono>{e.code}</Mono>
                  </div>
                  <p className="text-xs">{e.message}</p>
                  {e.when && (
                    <p className="text-xs text-muted-foreground">{e.when}</p>
                  )}
                  <div className="flex flex-wrap items-center gap-1">
                    {e.source_refs.map((ref) => (
                      <RefChip key={ref} refId={ref} />
                    ))}
                  </div>
                </div>
              </DataRow>
            ))}
          </DataList>
        );
      },
    },
    {
      id: "contrato",
      title: "Contrato",
      printTitle: "Convenciones del contrato",
      icon: <Plug />,
      searchable: false,
      tone: "blue",
      pattern: "dots",
      stat: { value: a.target.api_style.toUpperCase(), label: "estilo" },
      insight: (
        <>
          {a.target.base_path} · {a.openapi.operations_total} operaciones ·{" "}
          {a.target.auth.scheme}
        </>
      ),
      urgent: !a.target.auth.decided,
      urgentLabel: "autenticación por confirmar",
      render: () => <ContratoBlock artifact={a} />,
    },
    {
      id: "openapi",
      title: "OpenAPI",
      printTitle: "Documento OpenAPI",
      icon: <FileJson />,
      searchable: false,
      tone: "indigo",
      pattern: "lines",
      stat: { value: a.openapi.spec_version, label: "versión de la spec" },
      insight: (
        <>
          {Math.round(a.openapi.byte_size / 1024)} KB ·{" "}
          {a.validation.spec_valid ? "válido" : "con errores"}
        </>
      ),
      urgent: !a.validation.spec_valid,
      urgentLabel: "documento inválido",
      actions: (
        <div className="flex items-center gap-1.5 print:hidden">
          <Button
            variant="outline"
            size="sm"
            className="gap-1.5"
            onClick={() => {
              void navigator.clipboard.writeText(a.openapi.content);
              toast.success("Documento copiado");
            }}
          >
            <Copy className="h-3.5 w-3.5" />
            Copiar
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="gap-1.5"
            onClick={() =>
              download(
                a.openapi.content,
                `openapi-${job.job_id}.yaml`,
                "application/yaml",
              )
            }
          >
            <Download className="h-3.5 w-3.5" />
            YAML
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="gap-1.5"
            onClick={() => void descargarJson()}
          >
            <FileJson className="h-3.5 w-3.5" />
            JSON
          </Button>
        </div>
      ),
      render: ({ forPrint }) =>
        forPrint ? (
          // El YAML crudo no entra al PDF: mil líneas que nadie lee y que
          // duplican lo que el catálogo de endpoints cuenta mejor.
          <div className="space-y-1 text-xs">
            <p>
              Documento OpenAPI <b>{a.openapi.spec_version}</b> con{" "}
              <b>{a.openapi.operations_total}</b> operaciones (
              {Math.round(a.openapi.byte_size / 1024)} KB).
            </p>
            {a.openapi.checksum && (
              <p className="font-mono text-[11px] text-muted-foreground">
                {a.openapi.checksum}
              </p>
            )}
            <p className="text-muted-foreground">
              El documento completo se descarga desde la vista del contrato
              (sección OpenAPI), en YAML o JSON.
            </p>
          </div>
        ) : (
          <pre className="overflow-x-auto rounded-lg border bg-muted/30 p-3 font-mono text-[11px] leading-relaxed">
            {a.openapi.content}
          </pre>
        ),
    },
    {
      id: "validacion",
      title: "Validación",
      printTitle: "Validación de la especificación",
      icon: <ListChecks />,
      searchable: false,
      tone: "emerald",
      pattern: "dots",
      stat: {
        value: `${Object.values(a.validation.checks).filter(Boolean).length}/${
          Object.keys(a.validation.checks).length
        }`,
        label: "comprobaciones",
      },
      insight: a.validation.spec_valid
        ? `${a.validation.validator ?? "estructural"} · sin errores`
        : `${a.validation.errors.length} error(es)`,
      urgent: a.validation.errors.length > 0,
      urgentLabel: `${a.validation.errors.length} errores`,
      render: () => <ValidacionBlock artifact={a} />,
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
      printTitle: "Preguntas al líder técnico",
      icon: <MessagesSquare />,
      count: a.questions_for_tech_lead.length,
      tone: "amber",
      pattern: "waves",
      stat: {
        value: blockingRemaining,
        label: "bloqueantes pendientes",
      },
      insight:
        blockingRemaining > 0 ? (
          <span className="text-red-700">
            El contrato no habilita a construir hasta responderlas
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
          (items.some((q) => q.blocking && statusOf(q.id) === "pendiente") && !forPrint
            ? "enfocado"
            : "lista");

        if (modo === "enfocado" && !forPrint) {
          return (
            <FocusedQuestionFlow
              questions={items}
              statusOf={statusOf}
              ready={ready}
              readyLabel="Listo para los Agentes Backend y Frontend"
              nextAction={nextStepAction}
              onClose={hub.close}
              renderControls={(q, onAnswered) => (
                <TechLeadValidationControls
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
                    <TechLeadValidationControls
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
          kind="Especificación de API"
          title={`Contrato REST · ${a.openapi.operations_total} operaciones`}
          subtitle="Recursos, endpoints, esquemas de datos, matriz de autorización, catálogo de errores y trazabilidad de reglas."
          version="1.0.0"
          stats={[
            { label: "endpoints", value: String(a.endpoints.length) },
            { label: "esquemas", value: String(a.schemas.length) },
            {
              label: "reglas de acceso",
              value: String(a.authorization_matrix.length),
            },
            {
              label: "cobertura",
              value: `${Math.round(a.metrics.coverage * 100)}%`,
            },
          ]}
        />
        <PrintFooter title="Especificación de API" />

        {/* Barra superior de afinamiento + semáforo */}
        <div className="sticky top-0 z-10 border-b bg-background/95 px-6 py-4 backdrop-blur print:hidden">
          <div className={HUB_WIDTH}>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-2 text-sm">
              <span className="font-heading font-semibold">
                Contrato de API v1.0.0
              </span>
              <Badge variant="outline">
                {job.parent_job_id ? "v2 · afinamiento" : "v1 · original"}
              </Badge>
              <Badge variant="outline" className="gap-1">
                <Plug className="h-3 w-3" />
                {a.target.api_style.toUpperCase()} · OpenAPI{" "}
                {a.openapi.spec_version}
              </Badge>
              {!a.target.auth.decided && (
                <Badge
                  variant="outline"
                  className="border-amber-300 bg-amber-50 text-amber-700"
                  title="La arquitectura no decidió proveedor: se usó el estándar de la casa"
                >
                  autenticación por confirmar
                </Badge>
              )}
              {job.input_job_id && (
                <Link
                  href={`/agents/bd/jobs/${job.input_job_id}`}
                  className="text-xs text-muted-foreground underline-offset-2 hover:text-primary hover:underline"
                >
                  modelo de datos (<Mono>{job.input_job_id}</Mono>)
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
                  ? "Listo para los Agentes Backend y Frontend"
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
                  {puedeEditar && a.questions_for_tech_lead.length > 0 && (
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
                      onClick={() =>
                        download(
                          a.openapi.content,
                          `openapi-${job.job_id}.yaml`,
                          "application/yaml",
                        )
                      }
                    >
                      <FileJson className="h-3.5 w-3.5" />
                      OpenAPI
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      className="gap-1.5"
                      onClick={() =>
                        download(
                          JSON.stringify(a, null, 2),
                          `api-artifact-${job.job_id}.json`,
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
                              Regenerar contrato afinado
                            </Button>
                          }
                        />
                        <DialogContent>
                          <DialogHeader>
                            <DialogTitle>
                              Regenerar contrato afinado
                            </DialogTitle>
                            <DialogDescription>
                              Se creará un contrato hijo reinyectando tus
                              respuestas y se ejecutará el modelo real.
                            </DialogDescription>
                          </DialogHeader>
                          <div className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800">
                            Costo estimado: ~${a.metrics.cost.toFixed(4)}{" "}
                            (similar al contrato anterior). Esta acción consume
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
                  icon={<Route />}
                  value={a.endpoints.length}
                  label="endpoints"
                />
                <Stat
                  icon={<Layers />}
                  value={a.resources.length}
                  label="recursos"
                />
                <Stat
                  icon={<Braces />}
                  value={a.schemas.length}
                  label="esquemas"
                />
                <Stat
                  icon={<KeyRound />}
                  value={a.authorization_matrix.length}
                  label="reglas de acceso"
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

        <ArtifactPanel hub={hub} sections={sections} module="api" />
        <ArtifactPrintDoc sections={sections} active={printMode} />
      </div>
    </ArtifactNavProvider>
  );
}

// --- subcomponentes ----------------------------------------------------------

/** Una operación: método, ruta, propósito, parámetros, esquemas y códigos. */
function EndpointBlock({
  endpoint,
  requestSchema,
  responseSchema,
  sinPermiso,
}: {
  endpoint: ApiEndpoint;
  requestSchema?: ApiDataSchema;
  responseSchema?: ApiDataSchema;
  sinPermiso: boolean;
}) {
  const query = endpoint.parameters.filter((p) => p.location === "query");
  const path = endpoint.parameters.filter((p) => p.location === "path");

  return (
    <DataRow id={endpoint.id}>
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <MethodChip method={endpoint.method} />
          <span className="font-mono text-sm">{endpoint.path}</span>
          {endpoint.origin === "stated" && (
            <Badge
              variant="outline"
              className="border-sky-300 bg-sky-50 text-sky-700"
              title="El EF ya declaraba este endpoint"
            >
              declarado en el EF
            </Badge>
          )}
          {sinPermiso && (
            <Badge
              variant="outline"
              className="border-red-300 bg-red-50 text-red-700"
            >
              sin autorizar
            </Badge>
          )}
          <ConfidenceBadge value={endpoint.confidence ?? undefined} />
        </div>

        <p className="text-xs text-muted-foreground">
          <Mono>{endpoint.operation_id}</Mono> — {endpoint.purpose}
        </p>

        {path.length > 0 && (
          <p className="text-xs text-muted-foreground">
            <b>Ruta:</b>{" "}
            {path.map((p) => (
              <span key={p.id} className="mr-2">
                <Mono>{p.name}</Mono> ({p.logical_type})
              </span>
            ))}
          </p>
        )}

        {query.length > 0 && (
          <p className="text-xs text-muted-foreground">
            <b>Consulta:</b>{" "}
            {query.map((p) => (
              <span key={p.id} className="mr-2">
                <Mono>{p.name}</Mono>
              </span>
            ))}
          </p>
        )}

        <div className="flex flex-wrap items-center gap-2 text-xs">
          {requestSchema && (
            <span>
              <b>Entrada:</b> <Mono>{requestSchema.name}</Mono>
            </span>
          )}
          {responseSchema && (
            <span>
              <b>Salida:</b> <Mono>{responseSchema.name}</Mono>
              {endpoint.response_kind === "page" && " (paginada)"}
            </span>
          )}
          {endpoint.response_kind === "none" && (
            <span className="text-muted-foreground">Sin cuerpo de respuesta</span>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-1">
          {endpoint.status_codes.map((s) => (
            <span
              key={`${endpoint.id}-${s.code}`}
              className={cn(
                "rounded border px-1 py-px font-mono text-[10px]",
                s.code < 300
                  ? "border-emerald-300 bg-emerald-50 text-emerald-700"
                  : s.code < 500
                    ? "border-amber-300 bg-amber-50 text-amber-700"
                    : "border-red-300 bg-red-50 text-red-700",
              )}
              title={s.description ?? undefined}
            >
              {s.code}
            </span>
          ))}
        </div>

        <div className="flex flex-wrap items-center gap-1">
          {endpoint.auth_rule_refs.map((ref) => (
            <RefChip key={ref} refId={ref} />
          ))}
          {endpoint.rule_refs.map((ref) => (
            <RefChip key={ref} refId={ref} />
          ))}
          {endpoint.ef_api_ref && <RefChip refId={endpoint.ef_api_ref} />}
        </div>
      </div>
    </DataRow>
  );
}

/** Un recurso: tabla de origen, exposición y operaciones. */
function ResourceBlock({
  resource,
  endpoints,
}: {
  resource: ApiResource;
  endpoints: ApiEndpoint[];
}) {
  return (
    <DataRow id={resource.id}>
      <div className="space-y-1.5">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-heading text-sm font-semibold">
            {resource.display_name || resource.name}
          </span>
          <Mono>{resource.base_path}</Mono>
          <Badge
            variant="outline"
            className={cn(
              resource.exposure !== "crud" &&
                "border-amber-300 bg-amber-50 text-amber-700",
            )}
          >
            {EXPOSURE_LABEL[resource.exposure] ?? resource.exposure}
          </Badge>
          <RefChip refId={resource.table_ref} />
          {resource.entity_ref && <RefChip refId={resource.entity_ref} />}
          <ConfidenceBadge value={resource.confidence ?? undefined} />
        </div>
        {resource.description && (
          <p className="text-xs text-muted-foreground">{resource.description}</p>
        )}
        {resource.exposure_reason && (
          <p className="text-xs text-amber-700">{resource.exposure_reason}</p>
        )}
        <p className="text-xs text-muted-foreground">
          {endpoints.length === 0
            ? "Sin operaciones."
            : endpoints.map((e) => e.operation_id).join(" · ")}
        </p>
      </div>
    </DataRow>
  );
}

/** Un esquema de datos con sus campos y la columna de la que nace cada uno. */
function SchemaBlock({ schema }: { schema: ApiDataSchema }) {
  return (
    <DataRow id={schema.id}>
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-heading text-sm font-semibold">
            <Mono>{schema.name}</Mono>
          </span>
          <Badge variant="outline">
            {SCHEMA_KIND_LABEL[schema.kind] ?? schema.kind}
          </Badge>
        </div>
        {schema.description && (
          <p className="text-xs text-muted-foreground">{schema.description}</p>
        )}

        {schema.fields.length === 0 ? (
          <EmptyHint>Sin campos definidos todavía.</EmptyHint>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[30rem] text-xs">
              <thead>
                <tr className="border-b text-left text-muted-foreground">
                  <th className="py-1 pr-3 font-medium">Campo</th>
                  <th className="py-1 pr-3 font-medium">Tipo</th>
                  <th className="py-1 pr-3 font-medium">Oblig.</th>
                  <th className="py-1 pr-3 font-medium">Solo lect.</th>
                  <th className="py-1 font-medium">Columna</th>
                </tr>
              </thead>
              <tbody>
                {schema.fields.map((f) => (
                  <tr key={f.id} className="border-b border-border/50 align-top">
                    <td className="py-1 pr-3">
                      <Mono>{f.name}</Mono>
                      {f.pii && (
                        <span
                          className="ml-1 text-[10px] text-amber-700"
                          title="Dato personal"
                        >
                          PII
                        </span>
                      )}
                    </td>
                    <td className="py-1 pr-3">
                      {f.logical_type}
                      {f.format ? ` (${f.format})` : ""}
                    </td>
                    <td className="py-1 pr-3">{f.required ? "sí" : "no"}</td>
                    <td className="py-1 pr-3">{f.read_only ? "sí" : "no"}</td>
                    <td className="py-1">
                      {f.column_ref ? (
                        <RefChip refId={f.column_ref} />
                      ) : f.computed ? (
                        "calculado"
                      ) : (
                        "—"
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

/** Convenciones efectivas: con qué reglas se generó este contrato. */
function ContratoBlock({ artifact: a }: { artifact: ApiArtifact }) {
  const c = a.target.conventions;
  const filas: [string, string][] = [
    ["Estilo", a.target.api_style.toUpperCase()],
    ["Especificación", `OpenAPI ${a.openapi.spec_version}`],
    ["Prefijo", a.target.base_path],
    [
      "Autenticación",
      `${a.target.auth.scheme}${
        a.target.auth.provider ? ` · ${a.target.auth.provider}` : ""
      }${a.target.auth.decided ? "" : " (por confirmar)"}`,
    ],
    ["Idioma de las rutas", c.path_language === "es" ? "español" : "inglés"],
    ["Formato de rutas", `${c.path_case} · ${c.resource_number}`],
    ["Propiedades JSON", c.property_case],
    ["Envelope", c.envelope],
    ["Verbo de actualización", c.update_verb],
    [
      "Paginación",
      `${c.pagination.style} · ${c.pagination.limit_param}/${c.pagination.offset_param} (máx. ${c.pagination.max_limit})`,
    ],
    ["Orden", c.sort_param],
    ["Fechas", c.date_format],
    ["Decimales", c.decimal_as_string ? "como cadena" : "numéricos"],
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
      {a.target.conventions_source && (
        <p className="text-[11px] text-muted-foreground">
          Convenciones de <Mono>{a.target.conventions_source}</Mono>. Se guardan
          en el artefacto para que el contrato siga siendo interpretable si mañana
          cambian.
        </p>
      )}
    </div>
  );
}

/** Resultado de la validación en capas, con lo que se comprobó y lo que no. */
function ValidacionBlock({ artifact: a }: { artifact: ApiArtifact }) {
  const v = a.validation;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <Badge
          variant="outline"
          className={
            v.spec_valid
              ? "border-emerald-300 bg-emerald-50 text-emerald-700"
              : "border-red-300 bg-red-50 text-red-700"
          }
        >
          {v.spec_valid ? "especificación válida" : "especificación inválida"}
        </Badge>
        {v.validator && (
          <span className="text-muted-foreground">
            {v.validator}
            {v.validator_version ? ` ${v.validator_version}` : ""}
          </span>
        )}
      </div>

      <p className="text-[11px] text-muted-foreground">
        {v.runtime_checked
          ? "Comprobada además contra un runtime real."
          : "Comprobada por parseo y esquema. No se ejecutó contra un runtime: no se presenta como certificación lo que no lo es."}
      </p>

      <div className="grid gap-1 sm:grid-cols-2">
        {Object.entries(v.checks).map(([nombre, ok]) => (
          <div key={nombre} className="flex items-center gap-2 text-xs">
            <span
              className={cn(
                "h-1.5 w-1.5 rounded-full",
                ok ? "bg-emerald-500" : "bg-red-500",
              )}
            />
            <Mono>{nombre}</Mono>
          </div>
        ))}
      </div>

      {v.errors.length > 0 && (
        <div className="space-y-1">
          <GroupLabel>Errores</GroupLabel>
          {v.errors.map((e, i) => (
            <p key={`${e.code}-${i}`} className="text-xs text-red-700">
              <Mono>{e.code}</Mono> {e.message}
              {e.ref ? ` (${e.ref})` : ""}
            </p>
          ))}
        </div>
      )}

      {v.warnings.length > 0 && (
        <div className="space-y-1">
          <GroupLabel>Avisos</GroupLabel>
          {v.warnings.map((w, i) => (
            <p key={`${w.code}-${i}`} className="text-xs text-amber-700">
              <Mono>{w.code}</Mono> {w.message}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}

/** Cobertura con los huecos ENUMERADOS: un porcentaje solo no sirve para actuar. */
function CoberturaBlock({ artifact: a }: { artifact: ApiArtifact }) {
  const c = a.analysis.coverage;
  const filas: { label: string; hecho: number; total: number; faltan: string[] }[] =
    [
      {
        label: "Tablas expuestas",
        hecho: c.tables_exposed,
        total: c.tables_total,
        faltan: c.unexposed_table_refs,
      },
      {
        label: "Endpoints declarados en el EF",
        hecho: c.ef_apis_covered,
        total: c.ef_apis_total,
        faltan: c.uncovered_api_refs,
      },
      {
        label: "Celdas de la matriz CRUD",
        hecho: c.crud_cells_covered,
        total: c.crud_cells_total,
        faltan: c.uncovered_crud_refs,
      },
      {
        label: "Reglas con destino",
        hecho: c.rules_enforced,
        total: c.rules_total,
        faltan: c.unenforced_rule_refs,
      },
      {
        label: "Actores con acceso",
        hecho: c.actors_with_access,
        total: c.actors_total,
        faltan: c.actors_without_access,
      },
    ];

  return (
    <div className="space-y-2">
      {filas.map((f) => (
        <div key={f.label} className="space-y-0.5">
          <p className="text-xs">
            <b>{f.label}:</b> {f.hecho}/{f.total}
          </p>
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
    </div>
  );
}
