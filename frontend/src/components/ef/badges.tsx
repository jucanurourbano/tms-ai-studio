import { Badge } from "@/components/ui/badge";
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

const STATUS_STYLES: Record<JobStatus, string> = {
  PENDING: "border-slate-300 bg-slate-50 text-slate-700",
  RUNNING: "border-blue-300 bg-blue-50 text-blue-700",
  NEEDS_INPUT: "border-amber-300 bg-amber-50 text-amber-700",
  COMPLETED: "border-emerald-300 bg-emerald-50 text-emerald-700",
  COMPLETED_WITH_WARNINGS: "border-amber-300 bg-amber-50 text-amber-700",
  FAILED: "border-red-300 bg-red-50 text-red-700",
};

const STATUS_LABELS: Record<JobStatus, string> = {
  PENDING: "Pendiente",
  RUNNING: "En proceso",
  NEEDS_INPUT: "Requiere datos",
  COMPLETED: "Completado",
  COMPLETED_WITH_WARNINGS: "Completado con avisos",
  FAILED: "Falló",
};

export function JobStatusBadge({ status }: { status: JobStatus }) {
  return (
    <Badge variant="outline" className={STATUS_STYLES[status]}>
      {STATUS_LABELS[status] ?? status}
    </Badge>
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
