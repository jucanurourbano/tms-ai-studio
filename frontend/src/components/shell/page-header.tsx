import { AgentIconView } from "@/lib/agent-icons";
import type { AgentIcon } from "@/lib/isdf";
import { cn } from "@/lib/utils";

interface PageHeaderProps {
  /** Fase ISDF u otra etiqueta pequeña sobre el título. */
  eyebrow?: string;
  title: string;
  description?: React.ReactNode;
  /** Icono del agente (chip). */
  icon?: AgentIcon;
  /** "hero" = degradado de marca (landings); "plain" = chip + texto (subpáginas). */
  variant?: "hero" | "plain";
  /** Acción a la derecha (p. ej. botón "Nuevo análisis"). */
  action?: React.ReactNode;
  className?: string;
}

/**
 * Cabecera de página consistente: icono del agente + eyebrow + título + subtítulo.
 * Reutilizada por landings (hero, degradado violeta) y subpáginas (plain).
 */
export function PageHeader({
  eyebrow,
  title,
  description,
  icon,
  variant = "plain",
  action,
  className,
}: PageHeaderProps) {
  if (variant === "hero") {
    return (
      <div
        className={cn(
          "mb-6 overflow-hidden rounded-xl brand-gradient px-6 py-7 text-white shadow-sm",
          className,
        )}
      >
        <div className="flex items-start gap-4">
          {icon && (
            <div className="hidden h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-white/15 ring-1 ring-white/25 sm:flex">
              <AgentIconView icon={icon} className="h-6 w-6 text-white" />
            </div>
          )}
          <div className="min-w-0 flex-1">
            {eyebrow && (
              <div className="text-[11px] font-semibold uppercase tracking-widest text-white/80">
                {eyebrow}
              </div>
            )}
            <h1 className="font-heading text-2xl font-semibold tracking-tight">
              {title}
            </h1>
            {description && (
              <p className="mt-1 max-w-2xl text-sm text-white/85">{description}</p>
            )}
          </div>
          {action && <div className="shrink-0">{action}</div>}
        </div>
      </div>
    );
  }

  return (
    <header
      className={cn("mb-5 flex items-start justify-between gap-4", className)}
    >
      <div className="flex items-start gap-3">
        {icon && (
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-accent text-accent-foreground ring-1 ring-primary/10">
            <AgentIconView icon={icon} className="h-5 w-5" />
          </div>
        )}
        <div>
          {eyebrow && (
            <div className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground/80">
              {eyebrow}
            </div>
          )}
          <h1 className="font-heading text-xl font-semibold tracking-tight">
            {title}
          </h1>
          {description && (
            <p className="mt-0.5 text-sm text-muted-foreground">{description}</p>
          )}
        </div>
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </header>
  );
}
