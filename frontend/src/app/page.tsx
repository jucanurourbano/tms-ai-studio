import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { ISDF_NAV } from "@/lib/isdf";

export default function DashboardPage() {
  return (
    <div className="p-6 max-w-5xl">
      <header className="mb-6">
        <h1 className="text-xl font-heading font-semibold">TMS AI Studio</h1>
        <p className="text-sm text-muted-foreground">
          Asistencia al ciclo de vida del desarrollo mediante agentes de IA
          (ISDF).
        </p>
      </header>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {ISDF_NAV.map((phase) => (
          <Card key={phase.phase}>
            <CardHeader className="pb-2">
              <CardTitle className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                {phase.phase}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-1.5">
              {phase.agents.map((agent) =>
                agent.enabled && agent.href ? (
                  <Link
                    key={agent.key}
                    href={agent.href}
                    className="flex items-center justify-between rounded-md border px-3 py-2 text-sm hover:bg-accent transition-colors"
                  >
                    <span className="font-medium">{agent.name}</span>
                    <Badge className="bg-emerald-600">activo</Badge>
                  </Link>
                ) : (
                  <div
                    key={agent.key}
                    className="flex items-center justify-between rounded-md border border-dashed px-3 py-2 text-sm text-muted-foreground"
                  >
                    <span>{agent.name}</span>
                    <span className="text-[10px] uppercase tracking-wide">
                      próximamente
                    </span>
                  </div>
                ),
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
