"use client";

import { ChevronRight, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { AgentIconView } from "@/lib/agent-icons";
import { defaultOpenGroups, ISDF_NAV, type PhaseNav } from "@/lib/isdf";
import { usePersistentState } from "@/lib/use-persistent-state";
import { cn } from "@/lib/utils";

interface AppSidebarProps {
  /** Cierra el drawer en móvil tras navegar (Bloque 4). */
  onNavigate?: () => void;
}

export function AppSidebar({ onNavigate }: AppSidebarProps) {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = usePersistentState<boolean>(
    "sidebar:collapsed",
    false,
  );
  const [openGroups, setOpenGroups] = usePersistentState<Record<string, boolean>>(
    "sidebar:groups",
    defaultOpenGroups(),
  );

  const toggleGroup = (key: string) =>
    setOpenGroups((prev) => ({ ...prev, [key]: !(prev[key] ?? false) }));

  return (
    <aside
      data-collapsed={collapsed}
      className={cn(
        "flex h-full shrink-0 flex-col border-r bg-sidebar text-sidebar-foreground transition-[width] duration-300 ease-in-out",
        collapsed ? "w-[4.5rem]" : "w-64",
      )}
    >
      {/* Cabecera de marca (degradado violeta Urbano) */}
      <div
        className={cn(
          "brand-gradient flex items-center gap-3 px-4 py-4",
          collapsed && "justify-center px-0",
        )}
      >
        <Link
          href="/"
          onClick={onNavigate}
          className="flex items-center gap-3"
          title="TMS AI Studio"
        >
          <Image
            src="/logo-urbano.png"
            alt="Urbano"
            width={36}
            height={36}
            priority
            className="rounded-md ring-1 ring-white/30"
          />
          {!collapsed && (
            <div className="leading-tight text-white">
              <div className="font-heading text-sm font-semibold">TMS AI Studio</div>
              <div className="text-[11px] text-white/85">ISDF · Urbano TI</div>
            </div>
          )}
        </Link>
      </div>

      <nav className="flex-1 space-y-1 overflow-y-auto overflow-x-hidden px-2 py-4">
        {ISDF_NAV.map((phase) => (
          <SidebarGroup
            key={phase.key}
            phase={phase}
            collapsed={collapsed}
            open={openGroups[phase.key] ?? false}
            onToggle={() => toggleGroup(phase.key)}
            pathname={pathname}
            onNavigate={onNavigate}
          />
        ))}
      </nav>

      {/* Toggle de colapso total */}
      <div className="border-t p-2">
        <button
          type="button"
          onClick={() => setCollapsed((c) => !c)}
          title={collapsed ? "Expandir menú" : "Colapsar menú"}
          aria-label={collapsed ? "Expandir menú" : "Colapsar menú"}
          className={cn(
            "flex w-full items-center gap-2 rounded-md px-2 py-2 text-xs font-medium text-muted-foreground transition-colors hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground",
            collapsed && "justify-center",
          )}
        >
          {collapsed ? (
            <PanelLeftOpen className="h-4 w-4" />
          ) : (
            <>
              <PanelLeftClose className="h-4 w-4" />
              <span>Colapsar menú</span>
            </>
          )}
        </button>
      </div>
    </aside>
  );
}

interface SidebarGroupProps {
  phase: PhaseNav;
  collapsed: boolean;
  open: boolean;
  onToggle: () => void;
  pathname: string;
  onNavigate?: () => void;
}

function SidebarGroup({
  phase,
  collapsed,
  open,
  onToggle,
  pathname,
  onNavigate,
}: SidebarGroupProps) {
  // Colapsado total: los grupos se muestran siempre como lista de iconos, con un
  // separador tenue entre grupos (sin cabecera ni chevron).
  if (collapsed) {
    return (
      <div className="border-b border-sidebar-border/60 pb-1 last:border-b-0">
        <ul className="space-y-0.5 py-1">
          {phase.agents.map((agent) => (
            <SidebarItem
              key={agent.key}
              agent={agent}
              collapsed
              pathname={pathname}
              onNavigate={onNavigate}
            />
          ))}
        </ul>
      </div>
    );
  }

  return (
    <div>
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="flex w-full items-center justify-between rounded-md px-2 py-1.5 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground/80 transition-colors hover:text-foreground"
      >
        <span>{phase.phase}</span>
        <ChevronRight
          className={cn(
            "h-3.5 w-3.5 transition-transform duration-200",
            open && "rotate-90",
          )}
        />
      </button>
      <div
        className={cn(
          "grid transition-[grid-template-rows] duration-200 ease-in-out",
          open ? "grid-rows-[1fr]" : "grid-rows-[0fr]",
        )}
      >
        <ul className="space-y-0.5 overflow-hidden">
          {phase.agents.map((agent) => (
            <SidebarItem
              key={agent.key}
              agent={agent}
              collapsed={false}
              pathname={pathname}
              onNavigate={onNavigate}
            />
          ))}
        </ul>
      </div>
    </div>
  );
}

interface SidebarItemProps {
  agent: PhaseNav["agents"][number];
  collapsed: boolean;
  pathname: string;
  onNavigate?: () => void;
}

function SidebarItem({ agent, collapsed, pathname, onNavigate }: SidebarItemProps) {
  const active =
    !!agent.href &&
    (pathname === agent.href || pathname.startsWith(agent.href + "/"));

  if (!agent.enabled || !agent.href) {
    return (
      <li>
        <div
          title={collapsed ? `${agent.name} · próximamente` : undefined}
          className={cn(
            "flex cursor-not-allowed items-center gap-2 rounded-md px-2 py-1.5 text-sm text-muted-foreground/45",
            collapsed && "justify-center px-0",
          )}
        >
          <AgentIconView icon={agent.icon} className="h-4 w-4 shrink-0" />
          {!collapsed && (
            <>
              <span className="flex-1">{agent.name}</span>
              <span className="rounded bg-muted px-1 py-0.5 text-[9px] uppercase tracking-wide text-muted-foreground/70">
                pronto
              </span>
            </>
          )}
        </div>
      </li>
    );
  }

  return (
    <li>
      <Link
        href={agent.href}
        onClick={onNavigate}
        title={collapsed ? agent.name : undefined}
        aria-current={active ? "page" : undefined}
        className={cn(
          "flex items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors",
          collapsed && "justify-center px-0",
          active
            ? "bg-sidebar-accent font-semibold text-sidebar-accent-foreground"
            : "text-sidebar-foreground/80 hover:bg-sidebar-accent/50 hover:text-sidebar-accent-foreground",
        )}
      >
        <AgentIconView
          icon={agent.icon}
          className={cn("h-4 w-4 shrink-0", active && "text-primary")}
        />
        {!collapsed && <span className="flex-1">{agent.name}</span>}
      </Link>
    </li>
  );
}
