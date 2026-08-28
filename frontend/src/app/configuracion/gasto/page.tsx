"use client";

import { AlertTriangle, Loader2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { JobIdChip } from "@/components/history/job-id-chip";
import { PageContainer } from "@/components/shell/page-container";
import { PageHeader } from "@/components/shell/page-header";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { DataTable, type DataColumn } from "@/components/ui/data-table";
import { ApiError } from "@/lib/api/client";
import { gastoApi } from "@/lib/api/gasto";
import { useAuth } from "@/lib/auth/auth-context";
import {
  USAGE_SOURCE_STYLE,
  formatCount,
  formatPct,
  formatUsd,
  isUnattributed,
  progressTone,
  progressWidth,
  stageLabel,
} from "@/lib/gasto";
import type {
  MonthlySpend,
  SpendBreakdownRow,
  SpendTopJob,
} from "@/lib/types/gasto";

/**
 * Un tope contra el que se avanza. Se pintan dos: el **objetivo**, que es el
 * número contra el que hay que comparar, y el techo duro al lado, para ver
 * cuánto margen queda antes de que el freno actúe.
 */
function CapMeter({
  label,
  hint,
  spent,
  cap,
  pct,
}: {
  label: string;
  hint: string;
  spent: string;
  cap: string;
  pct: number | null;
}) {
  return (
    <Card size="sm" className="px-4">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-meta-foreground">
          {label}
        </span>
        <span className="font-mono text-xs tabular-nums text-muted-foreground">
          {formatPct(pct)}
        </span>
      </div>
      <div className="mt-1 font-heading text-xl font-semibold tabular-nums">
        {formatUsd(spent)}
        <span className="ml-1 text-sm font-normal text-muted-foreground">
          / {formatUsd(cap)}
        </span>
      </div>
      <div
        className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-muted"
        role="img"
        aria-label={`${label}: ${formatPct(pct)}`}
      >
        <div
          className={`h-full rounded-full transition-[width] ${progressTone(pct)}`}
          style={{ width: progressWidth(pct) }}
        />
      </div>
      <p className="mt-2 text-xs text-muted-foreground">{hint}</p>
    </Card>
  );
}

/**
 * El sello de honestidad de la cifra. Se muestra SIEMPRE, también cuando todo
 * está medido: un aviso que solo aparece cuando algo va mal enseña a ignorarlo,
 * y su ausencia se confunde con "no se comprobó".
 */
function UsageSourceNote({ data }: { data: MonthlySpend }) {
  const style = USAGE_SOURCE_STYLE[data.usage_source];
  const aproximado =
    data.usage_source === "mixto" || data.usage_source === "estimado";
  return (
    <Card size="sm" className={aproximado ? "px-4 ring-amber-300/70" : "px-4"}>
      <div className="flex items-center gap-2">
        {aproximado && (
          <AlertTriangle className="h-4 w-4 shrink-0 text-amber-600" />
        )}
        <Badge variant="outline" className={style.badge}>
          {style.label}
        </Badge>
        {aproximado && (
          <span className="font-mono text-xs tabular-nums text-amber-700">
            {(data.estimated_fraction * 100).toFixed(1)}% del importe
          </span>
        )}
      </div>
      <p className="mt-2 text-xs text-muted-foreground">{style.hint}</p>
      {aproximado && (
        <p className="mt-1 text-xs text-muted-foreground">
          {formatCount(data.estimated_calls)} de {formatCount(data.calls)}{" "}
          llamadas · {formatUsd(data.estimated_cost_usd, 4)} de{" "}
          {formatUsd(data.spent_usd, 4)}.
        </p>
      )}
    </Card>
  );
}

const COSTO_Y_LLAMADAS: DataColumn<SpendBreakdownRow>[] = [
  {
    key: "cost",
    label: "Costo",
    numeric: true,
    render: (row) => formatUsd(row.cost_usd, 4),
  },
  {
    key: "calls",
    label: "Llamadas",
    numeric: true,
    render: (row) => formatCount(row.calls),
  },
  {
    key: "estimated",
    label: "Estimadas",
    numeric: true,
    render: (row) =>
      row.estimated_calls > 0 ? (
        <span className="text-amber-700">
          {formatCount(row.estimated_calls)}
        </span>
      ) : (
        <span className="text-muted-foreground">—</span>
      ),
  },
];

const AGENT_COLUMNS: DataColumn<SpendBreakdownRow>[] = [
  {
    key: "agent",
    label: "Agente",
    cardRole: "title",
    render: (row) => <span className="font-medium">{row.agent_role}</span>,
  },
  ...COSTO_Y_LLAMADAS,
];

const STAGE_COLUMNS: DataColumn<SpendBreakdownRow>[] = [
  {
    key: "stage",
    label: "Nodo",
    cardRole: "title",
    render: (row) => (
      <span
        className={
          isUnattributed(row.stage)
            ? "italic text-muted-foreground"
            : "font-mono text-xs font-medium"
        }
        title={
          isUnattributed(row.stage)
            ? "Pases que no llevan etiqueta de nodo. Su gasto se atribuye al agente, no a un nodo concreto."
            : undefined
        }
      >
        {stageLabel(row.stage)}
      </span>
    ),
  },
  {
    key: "agent",
    label: "Agente",
    cardRole: "meta",
    render: (row) => (
      <span className="text-muted-foreground">{row.agent_role}</span>
    ),
  },
  ...COSTO_Y_LLAMADAS,
];

const JOB_COLUMNS: DataColumn<SpendTopJob>[] = [
  {
    key: "job",
    label: "Job",
    cardRole: "title",
    render: (row) => <JobIdChip id={row.job_id} />,
  },
  {
    key: "agent",
    label: "Agente",
    cardRole: "meta",
    render: (row) => (
      <span className="text-muted-foreground">{row.agent_role}</span>
    ),
  },
  {
    key: "cost",
    label: "Costo",
    numeric: true,
    render: (row) => formatUsd(row.cost_usd, 4),
  },
  {
    key: "calls",
    label: "Llamadas",
    numeric: true,
    render: (row) => formatCount(row.calls),
  },
];

export default function GastoPage() {
  const { can } = useAuth();
  const puedeVer = can("config");
  const [data, setData] = useState<MonthlySpend | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // El estado se actualiza solo en callbacks async (convención del proyecto:
  // nunca setState síncrono dentro de un efecto). `loading` arranca en true.
  const fetchData = useCallback(() => {
    gastoApi
      .monthly()
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((err) =>
        setError(
          err instanceof ApiError
            ? err.message
            : "No se pudo cargar el gasto del mes.",
        ),
      )
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (puedeVer) fetchData();
  }, [puedeVer, fetchData]);

  if (!puedeVer) {
    return (
      <PageContainer variant="notice">
        <Card className="px-4 py-6 text-sm text-muted-foreground">
          Tu rol no tiene acceso a la configuración de la plataforma.
        </Card>
      </PageContainer>
    );
  }

  return (
    <PageContainer>
      <PageHeader
        module="config"
        eyebrow="Configuración"
        title="Control de gasto"
        description={
          data
            ? `Mes ${data.month}, de calendario en ${data.timezone}. El freno actúa antes de cada llamada al modelo; esto es lo que va protegiendo.`
            : "Gasto del mes en llamadas al modelo."
        }
      />

      {loading && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Cargando el libro mayor…
        </div>
      )}

      {error && (
        <Card className="px-4 py-3 text-sm text-destructive ring-destructive/30">
          {error}
        </Card>
      )}

      {data && !error && (
        <div className="space-y-6">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            <CapMeter
              label="Objetivo del mes"
              hint="No bloquea nunca. Es el número contra el que hay que comparar toda cifra."
              spent={data.spent_usd}
              cap={data.target_usd}
              pct={data.target_pct}
            />
            <CapMeter
              label="Techo del mes"
              hint="Tope duro: al alcanzarlo, las llamadas se niegan antes de gastar."
              spent={data.spent_usd}
              cap={data.cap_usd}
              pct={data.cap_pct}
            />
            <UsageSourceNote data={data} />
          </div>

          <Card size="sm" className="px-4">
            <div className="flex flex-wrap gap-x-8 gap-y-2 text-sm">
              <Stat label="Llamadas" value={formatCount(data.calls)} />
              <Stat
                label="Tokens de entrada"
                value={formatCount(data.input_tokens)}
              />
              <Stat
                label="Tokens de salida"
                value={formatCount(data.output_tokens)}
              />
              <Stat
                label="Freno por corrida"
                value={formatUsd(data.job_cap_usd)}
              />
            </div>
          </Card>

          <Section
            title="Por nodo del grafo"
            hint="El desglose con el que se mide un recorte: qué costaba un nodo antes y qué cuesta después. Las filas sin nodo son pases que no llevan etiqueta; su gasto se ve aquí en vez de desaparecer."
          >
            <DataTable
              columns={STAGE_COLUMNS}
              rows={data.by_stage}
              rowKey={(r) => `${r.agent_role}::${r.stage ?? ""}`}
              empty="Ninguna llamada anotada este mes."
              zebra
            />
          </Section>

          <Section title="Por agente">
            <DataTable
              columns={AGENT_COLUMNS}
              rows={data.by_agent}
              rowKey={(r) => r.agent_role}
              empty="Ninguna llamada anotada este mes."
              zebra
            />
          </Section>

          <Section
            title="Corridas más caras"
            hint="Solo las llamadas que pertenecen a un job. La ingesta de documentos del inventario no tiene job: cuenta en el total y en «por agente»."
          >
            <DataTable
              columns={JOB_COLUMNS}
              rows={data.top_jobs}
              rowKey={(r) => r.job_id}
              empty="Ningún job con gasto anotado este mes."
              zebra
            />
          </Section>
        </div>
      )}
    </PageContainer>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] font-semibold uppercase tracking-widest text-meta-foreground">
        {label}
      </div>
      <div className="font-mono text-sm tabular-nums">{value}</div>
    </div>
  );
}

function Section({
  title,
  hint,
  children,
}: {
  title: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <section>
      <h2 className="font-heading text-base font-semibold tracking-tight">
        {title}
      </h2>
      {hint && (
        <p className="prose-measure mb-2 mt-0.5 text-xs text-muted-foreground">
          {hint}
        </p>
      )}
      <div className={hint ? "" : "mt-2"}>{children}</div>
    </section>
  );
}
