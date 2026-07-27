"use client";

import { ArrowRight } from "lucide-react";
import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { AgentIconView } from "@/lib/agent-icons";
import { useAuth } from "@/lib/auth/auth-context";
import { type FlatAgent, flatAgentsForModules } from "@/lib/isdf";
import { accentOf } from "@/lib/module-accent";
import { cn } from "@/lib/utils";

/**
 * Grid de agentes del ISDF: cada agente es una tarjeta con su icono (contenedor
 * con glow violeta), nombre, descripción y badge de estado. Los activos son
 * clicables con hover elevado; los próximos se muestran atenuados.
 *
 * Solo se muestran los agentes cuyo módulo el usuario puede ver: el dashboard
 * refleja el mismo alcance que la sidebar, sin tarjetas que lleven a un 403.
 */
export function AgentsGrid() {
  const { modules } = useAuth();
  const agents = flatAgentsForModules(modules);
  if (agents.length === 0) return null;
  return (
    <section className="mb-6">
      <h2 className="mb-3 font-heading text-base font-semibold tracking-tight">
        Agentes
      </h2>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {agents.map((agent) => (
          <AgentCard key={agent.key} agent={agent} />
        ))}
      </div>
    </section>
  );
}

function AgentCard({ agent }: { agent: FlatAgent }) {
  const active = agent.enabled && !!agent.href;
  const accent = accentOf(agent.module);

  const inner = (
    <Card
      className={cn(
        "h-full gap-0 transition-all duration-200",
        active
          ? "group-hover:-translate-y-0.5 group-hover:shadow-lg group-hover:ring-primary/30"
          : "bg-muted/30",
      )}
    >
      <div className="flex items-start gap-3 px-(--card-spacing)">
        <div
          className={cn(
            "flex h-11 w-11 shrink-0 items-center justify-center rounded-xl ring-1 transition-colors [&_svg]:h-5 [&_svg]:w-5",
            // Fondo tenue + icono en el tono pleno del módulo (acento suave).
            active
              ? cn("icon-glow ring-1", accent.soft, accent.ring)
              : "bg-muted text-muted-foreground/60 ring-border",
          )}
        >
          <AgentIconView icon={agent.icon} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-[10px] font-semibold uppercase tracking-widest text-meta-foreground">
            {agent.phase}
          </div>
          <CardTitle
            className={cn(
              "flex items-center justify-between gap-2",
              !active && "text-muted-foreground",
            )}
          >
            <span className="truncate">{agent.name}</span>
            {active ? (
              <ArrowRight
                className={cn(
                  "h-4 w-4 shrink-0 text-muted-foreground transition-all group-hover:translate-x-0.5",
                  accent.groupHoverText,
                )}
              />
            ) : null}
          </CardTitle>
        </div>
      </div>

      <CardDescription className="mt-2 px-(--card-spacing) leading-relaxed">
        {agent.description}
      </CardDescription>

      <div className="mt-3 px-(--card-spacing)">
        {active ? (
          <Badge variant="outline" className={cn("border-transparent", accent.soft)}>
            activo
          </Badge>
        ) : (
          <Badge
            variant="outline"
            className="border-dashed text-muted-foreground"
          >
            próximamente
          </Badge>
        )}
      </div>
    </Card>
  );

  if (active && agent.href) {
    return (
      <Link
        href={agent.href}
        className="group block h-full rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
      >
        {inner}
      </Link>
    );
  }

  return (
    <div
      className="h-full cursor-not-allowed"
      aria-disabled
      title={`${agent.name} · próximamente`}
    >
      {inner}
    </div>
  );
}
