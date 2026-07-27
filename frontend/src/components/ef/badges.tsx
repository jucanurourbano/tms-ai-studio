import { Badge } from "@/components/ui/badge";
import { StatusPill, type StatusTone } from "@/components/ui/status-pill";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { Audience, JobStatus, Origin } from "@/lib/types/ef";
import { cn } from "@/lib/utils";

/** Texto monoespaciado para ids, refs y evidencia. */
export function Mono({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <span className={cn("font-mono text-xs", className)}>{children}</span>;
}

export function OriginBadge({ origin }: { origin?: Origin | null }) {
  const derived = origin === "derived";
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <Badge
            variant="outline"
            className={cn(
              "cursor-help",
              derived
                ? "border-sky-300 bg-sky-50 text-sky-700"
                : "text-muted-foreground",
            )}
          >
            {derived ? "derivado" : "declarado"}
          </Badge>
        }
      />
      <TooltipContent>
        {derived
          ? "Derivado: inferido por el agente a partir de evidencia implícita."
          : "Declarado: afirmado explícitamente en el documento de origen."}
      </TooltipContent>
    </Tooltip>
  );
}

export function ConfidenceBadge({ value }: { value?: number | null }) {
  if (value === null || value === undefined) {
    return <span className="text-xs text-muted-foreground">—</span>;
  }
  const pct = Math.round(value * 100);
  const cls =
    value >= 0.8
      ? "border-emerald-300 bg-emerald-50 text-emerald-700"
      : value >= 0.5
        ? "border-amber-300 bg-amber-50 text-amber-700"
        : "border-red-300 bg-red-50 text-red-700";
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <Badge variant="outline" className={cn("cursor-help font-mono", cls)}>
            {pct}%
          </Badge>
        }
      />
      <TooltipContent>
        Confianza del agente en este ítem ({pct}%). Por debajo de 80% conviene
        revisarlo.
      </TooltipContent>
    </Tooltip>
  );
}

const STATUS_LABELS: Record<JobStatus, string> = {
  PENDING: "Pendiente",
  RUNNING: "En proceso",
  NEEDS_INPUT: "Requiere datos",
  COMPLETED: "Completado",
  COMPLETED_WITH_WARNINGS: "Completado con avisos",
  FAILED: "Falló",
};

/** Tono funcional de cada estado de job (el color significa, no decora). */
const STATUS_TONE: Record<JobStatus, StatusTone> = {
  PENDING: "neutral",
  RUNNING: "info",
  NEEDS_INPUT: "warning",
  COMPLETED: "success",
  COMPLETED_WITH_WARNINGS: "warning",
  FAILED: "error",
};

export function JobStatusBadge({ status }: { status: JobStatus }) {
  const enCurso = status === "RUNNING" || status === "PENDING";
  return (
    <StatusPill tone={STATUS_TONE[status] ?? "neutral"} pulse={enCurso}>
      {STATUS_LABELS[status] ?? status}
    </StatusPill>
  );
}

export function AudienceBadge({ audience }: { audience: Audience }) {
  const cls =
    audience === "negocio"
      ? "border-violet-300 bg-violet-50 text-violet-700"
      : "border-cyan-300 bg-cyan-50 text-cyan-700";
  return (
    <Badge variant="outline" className={cls}>
      {audience === "negocio" ? "negocio" : "técnico"}
    </Badge>
  );
}
