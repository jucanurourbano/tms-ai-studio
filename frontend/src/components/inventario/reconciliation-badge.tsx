"use client";

import { AlertTriangle } from "lucide-react";

import {
  styleOf,
  summaryChips,
  summaryHeadline,
  type ReconciliationRef,
  type ReconciliationSummary,
} from "@/lib/reconciliation";
import { cn } from "@/lib/utils";

/**
 * Badge del veredicto de reconciliación de UN elemento.
 *
 * El `title` lleva el motivo completo: el badge dice QUÉ se decidió y el tooltip
 * POR QUÉ. Un color sin explicación obligaría a fiarse de una decisión
 * automática sobre un sistema de producción.
 */
export function ReconciliationBadge({
  reconciliation,
  className,
}: {
  reconciliation?: ReconciliationRef | null;
  className?: string;
}) {
  if (!reconciliation) return null;
  const estilo = styleOf(reconciliation.status);
  return (
    <span
      title={reconciliation.reason || estilo.hint}
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ring-1",
        estilo.badge,
        className,
      )}
    >
      <span className={cn("h-1.5 w-1.5 rounded-full", estilo.dot)} />
      {estilo.label}
      {reconciliation.blocking && <AlertTriangle className="h-3 w-3" />}
    </span>
  );
}

/**
 * Detalle del veredicto: lo existente al lado de lo propuesto.
 *
 * Es lo que hace revisable la decisión. Sin enseñar contra QUÉ se emparejó y con
 * qué parecido, un `reuse` es un acto de fe.
 */
export function ReconciliationDetail({
  reconciliation,
}: {
  reconciliation?: ReconciliationRef | null;
}) {
  if (!reconciliation) return null;
  const { matched, missing, reason, status } = reconciliation;
  return (
    <div className="space-y-2 rounded-md border bg-muted/30 p-3 text-xs">
      <div className="flex items-center gap-2">
        <ReconciliationBadge reconciliation={reconciliation} />
        <span className="text-muted-foreground">{styleOf(status).hint}</span>
      </div>
      <p className="text-muted-foreground">{reason}</p>

      {matched && (
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
          <dt className="text-meta-foreground">Existente</dt>
          <dd className="font-mono">{matched.name}</dd>
          <dt className="text-meta-foreground">Sistema</dt>
          <dd>
            {matched.system_name}
            {matched.asset_name ? ` · ${matched.asset_name}` : ""}
          </dd>
          <dt className="text-meta-foreground">Parecido</dt>
          <dd>
            nombre {(matched.name_score * 100).toFixed(0)}%
            {matched.structure_score !== null &&
              ` · estructura ${(matched.structure_score * 100).toFixed(0)}%`}
          </dd>
        </dl>
      )}

      {missing && missing.length > 0 && (
        <div>
          <p className="text-meta-foreground">Le falta</p>
          <p className="font-mono">{missing.join(", ")}</p>
        </div>
      )}
    </div>
  );
}

/**
 * Franja de resumen para la cabecera del artefacto.
 *
 * Distingue explícitamente los tres casos que NO son lo mismo: la fase no corrió,
 * corrió sin encontrar nada, o reconcilió. Leer un diseño como "validado contra
 * el inventario" cuando nadie lo comparó con nada sería el peor malentendido
 * posible de esta pantalla.
 */
export function ReconciliationSummaryBar({
  summary,
}: {
  summary?: ReconciliationSummary | null;
}) {
  const chips = summaryChips(summary ?? null);
  const noEjecutada = !summary?.performed;

  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-2 rounded-lg border px-3 py-2 text-xs",
        noEjecutada ? "border-dashed bg-muted/20" : "bg-card",
      )}
    >
      <span className={cn(noEjecutada && "text-muted-foreground")}>
        {summaryHeadline(summary ?? null)}
      </span>
      {chips.map(({ status, count }) => {
        const estilo = styleOf(status);
        return (
          <span
            key={status}
            title={estilo.hint}
            className={cn(
              "inline-flex items-center gap-1 rounded-full px-2 py-0.5 font-semibold ring-1",
              estilo.badge,
            )}
          >
            <span className={cn("h-1.5 w-1.5 rounded-full", estilo.dot)} />
            {count} {estilo.label.toLowerCase()}
          </span>
        );
      })}
    </div>
  );
}
