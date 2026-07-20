"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { ISDF_NAV } from "@/lib/isdf";
import { cn } from "@/lib/utils";

export function AppSidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-60 shrink-0 border-r bg-sidebar text-sidebar-foreground flex flex-col">
      {/* Cabecera de marca (degradado violeta Urbano) */}
      <div className="brand-gradient px-4 py-4">
        <Link href="/" className="flex items-center gap-3">
          <Image
            src="/logo-urbano.png"
            alt="Urbano"
            width={36}
            height={36}
            priority
            className="rounded-md ring-1 ring-white/30"
          />
          <div className="leading-tight text-white">
            <div className="font-heading font-semibold text-sm">
              TMS AI Studio
            </div>
            <div className="text-[11px] text-white/85">ISDF · Urbano TI</div>
          </div>
        </Link>
      </div>

      <nav className="flex-1 overflow-y-auto px-2 py-4 space-y-5">
        {ISDF_NAV.map((phase) => (
          <div key={phase.phase}>
            <div className="px-2 pb-1.5 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground/80">
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
                      <div className="flex items-center justify-between rounded-md px-2 py-1.5 text-sm text-muted-foreground/50 cursor-not-allowed">
                        <span>{agent.name}</span>
                        <span className="text-[9px] uppercase tracking-wide rounded bg-muted px-1 py-0.5 text-muted-foreground/70">
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
                        "flex items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors",
                        active
                          ? "bg-sidebar-accent text-sidebar-accent-foreground font-semibold"
                          : "text-sidebar-foreground/80 hover:bg-sidebar-accent/50 hover:text-sidebar-accent-foreground",
                      )}
                    >
                      <span
                        className={cn(
                          "h-1.5 w-1.5 rounded-full",
                          active ? "bg-primary" : "bg-transparent",
                        )}
                      />
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
