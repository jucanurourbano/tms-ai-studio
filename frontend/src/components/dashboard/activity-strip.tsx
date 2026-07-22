"use client";

import { CircleDollarSign, LayoutList, TrendingUp } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { JobStatusBadge } from "@/components/ef/badges";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { AgentIconView } from "@/lib/agent-icons";
import { efApi } from "@/lib/api/ef";
import { scrumApi } from "@/lib/api/scrum";
import {
  type ActivityRow,
  countThisMonth,
  formatCost,
  isSameMonth,
  mergeActivity,
  type Semaforo,
  semaforoFor,
} from "@/lib/dashboard";
import { relativeTime } from "@/lib/format";
import type { AgentIcon } from "@/lib/isdf";
import { cn } from "@/lib/utils";

const LIST_LIMIT = 20;
const RECENT_COUNT = 5;

/** Estados cuyo costo real ya está consolidado (vale la pena sumar). */
const COSTED_STATUSES = new Set(["COMPLETED", "COMPLETED_WITH_WARNINGS"]);

interface MonthMetrics {
  analyses: number;
  cost: number;
  total: number;
}

const SEMAFORO_STYLES: Record<Semaforo, string> = {
  green: "bg-emerald-500",
  amber: "bg-amber-500",
  red: "bg-red-500",
  blue: "bg-blue-500",
};

const SEMAFORO_LABELS: Record<Semaforo, string> = {
  green: "Completado",
  amber: "Con avisos o requiere datos",
  red: "Falló",
  blue: "En proceso",
};

function SemaforoDot({ row }: { row: ActivityRow }) {
  const s = semaforoFor(row.status);
  const running = row.status === "RUNNING" || row.status === "PENDING";
  return (
    <span
      className={cn(
        "inline-block h-2 w-2 shrink-0 rounded-full",
        SEMAFORO_STYLES[s],
        running && "animate-pulse",
      )}
      title={SEMAFORO_LABELS[s]}
      aria-label={SEMAFORO_LABELS[s]}
    />
  );
}

function agentIconOf(agent: ActivityRow["agent"]): AgentIcon {
  return agent === "ef" ? "file-search" : "kanban";
}

function ActivityItem({ row }: { row: ActivityRow }) {
  return (
    <Link
      href={row.href}
      className="flex items-center gap-3 rounded-lg px-2 py-2 transition-colors hover:bg-accent/60"
    >
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary ring-1 ring-primary/15 [&_svg]:h-4 [&_svg]:w-4">
        <AgentIconView icon={agentIconOf(row.agent)} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate text-sm font-medium">
            {row.title?.trim() || "(sin título)"}
          </span>
          <span className="shrink-0 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground/70">
            {row.agent === "ef" ? "EF" : "Scrum"}
          </span>
        </div>
        <div className="text-xs text-muted-foreground">
          {relativeTime(row.created_at)}
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <SemaforoDot row={row} />
        <JobStatusBadge status={row.status} />
      </div>
    </Link>
  );
}

function MetricTile({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-lg border bg-muted/30 p-3">
      <div className="flex items-center gap-1.5 text-xs text-muted-foreground [&_svg]:h-3.5 [&_svg]:w-3.5">
        {icon}
        {label}
      </div>
      <div className="mt-1 font-heading text-xl font-semibold tabular-nums">
        {value}
      </div>
    </div>
  );
}

/**
 * Franja de actividad del dashboard: últimos jobs (EF + Scrum) con estado y
 * semáforo, junto a mini-métricas del mes (análisis realizados y costo
 * acumulado, sumando `metrics.cost` de los jobs del mes).
 */
export function ActivityStrip() {
  const [rows, setRows] = useState<ActivityRow[]>([]);
  const [metrics, setMetrics] = useState<MonthMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const [ef, scrum] = await Promise.all([
          efApi.listJobs(LIST_LIMIT),
          scrumApi.listJobs(LIST_LIMIT),
        ]);
        if (cancelled) return;

        const merged = mergeActivity(ef.items, scrum.items);
        setRows(merged.slice(0, RECENT_COUNT));

        const now = Date.now();
        const analyses = countThisMonth(merged, now);
        const total = (ef.total ?? 0) + (scrum.total ?? 0);

        // Costo del mes: sumar metrics.cost de los jobs consolidados del mes.
        // El listado no trae métricas, así que se consulta el detalle de cada uno.
        const costTargets = merged.filter(
          (r) => isSameMonth(r.created_at, now) && COSTED_STATUSES.has(r.status),
        );
        const details = await Promise.allSettled(
          costTargets.map((r) =>
            r.agent === "ef" ? efApi.getJob(r.job_id) : scrumApi.getJob(r.job_id),
          ),
        );
        const cost = details.reduce((acc, d) => {
          if (d.status !== "fulfilled") return acc;
          return acc + (d.value.metrics?.cost ?? 0);
        }, 0);

        if (!cancelled) setMetrics({ analyses, cost, total });
      } catch {
        if (!cancelled)
          setError("No se pudo cargar la actividad reciente.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section>
      <h2 className="mb-3 font-heading text-lg font-semibold tracking-tight">
        Actividad reciente
      </h2>

      <div className="grid gap-4 lg:grid-cols-3">
        {/* Lista de últimos jobs (2/3) */}
        <Card className="lg:col-span-2">
          <div className="px-(--card-spacing)">
            {loading ? (
              <div className="space-y-3 py-1">
                {Array.from({ length: RECENT_COUNT }).map((_, i) => (
                  <div key={i} className="flex items-center gap-3">
                    <Skeleton className="h-8 w-8 rounded-lg" />
                    <div className="flex-1">
                      <Skeleton className="h-4 w-48" />
                      <Skeleton className="mt-1 h-3 w-24" />
                    </div>
                    <Skeleton className="h-5 w-24" />
                  </div>
                ))}
              </div>
            ) : error ? (
              <p className="py-6 text-center text-sm text-muted-foreground">
                {error}
              </p>
            ) : rows.length === 0 ? (
              <p className="py-6 text-center text-sm text-muted-foreground">
                Aún no hay análisis. Empieza con un{" "}
                <Link
                  href="/agents/ef/new"
                  className="font-medium text-primary underline-offset-4 hover:underline"
                >
                  nuevo análisis EF
                </Link>
                .
              </p>
            ) : (
              <div className="-mx-2 divide-y divide-border/60">
                {rows.map((row) => (
                  <ActivityItem key={`${row.agent}-${row.job_id}`} row={row} />
                ))}
              </div>
            )}
          </div>
        </Card>

        {/* Mini-métricas del mes (1/3) */}
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-1">
          {loading || !metrics ? (
            <>
              <Skeleton className="h-[4.75rem] rounded-lg" />
              <Skeleton className="h-[4.75rem] rounded-lg" />
              <Skeleton className="hidden h-[4.75rem] rounded-lg lg:block" />
            </>
          ) : (
            <>
              <MetricTile
                icon={<LayoutList />}
                label="Análisis este mes"
                value={String(metrics.analyses)}
              />
              <MetricTile
                icon={<CircleDollarSign />}
                label="Costo del mes"
                value={formatCost(metrics.cost)}
              />
              <MetricTile
                icon={<TrendingUp />}
                label="Total histórico"
                value={String(metrics.total)}
              />
            </>
          )}
        </div>
      </div>
    </section>
  );
}
