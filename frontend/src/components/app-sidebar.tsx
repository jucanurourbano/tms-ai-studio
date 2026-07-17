"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { ISDF_NAV } from "@/lib/isdf";
import { cn } from "@/lib/utils";

export function AppSidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-60 shrink-0 border-r bg-sidebar text-sidebar-foreground flex flex-col">
      <div className="px-4 py-4 border-b">
        <Link href="/" className="block">
          <div className="font-heading font-semibold text-sm leading-tight">
            TMS AI Studio
          </div>
          <div className="text-xs text-muted-foreground">ISDF · Urbano TI</div>
        </Link>
      </div>

      <nav className="flex-1 overflow-y-auto px-2 py-3 space-y-4">
        {ISDF_NAV.map((phase) => (
          <div key={phase.phase}>
            <div className="px-2 pb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              {phase.phase}
            </div>
            <ul className="space-y-0.5">
              {phase.agents.map((agent) => {
                const active =
                  agent.href &&
                  (pathname === agent.href ||
                    pathname.startsWith(agent.href + "/"));

                if (!agent.enabled || !agent.href) {
                  return (
                    <li key={agent.key}>
                      <div className="flex items-center justify-between rounded-md px-2 py-1.5 text-sm text-muted-foreground/60 cursor-not-allowed">
                        <span>{agent.name}</span>
                        <span className="text-[9px] uppercase tracking-wide rounded bg-muted px-1 py-0.5">
                          próximamente
                        </span>
                      </div>
                    </li>
                  );
                }

                return (
                  <li key={agent.key}>
                    <Link
                      href={agent.href}
                      className={cn(
                        "flex items-center rounded-md px-2 py-1.5 text-sm transition-colors",
                        active
                          ? "bg-sidebar-accent text-sidebar-accent-foreground font-medium"
                          : "hover:bg-sidebar-accent/60",
                      )}
                    >
                      {agent.name}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      <div className="px-4 py-3 border-t text-[10px] text-muted-foreground">
        v1 · tema claro
      </div>
    </aside>
  );
}
