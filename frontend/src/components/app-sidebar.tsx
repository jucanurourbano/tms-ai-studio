"use client";

import {
  ChevronRight,
  LogOut,
  PanelLeftClose,
  PanelLeftOpen,
  Users,
} from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect } from "react";

import { useAuth } from "@/lib/auth/auth-context";
import { AgentIconView } from "@/lib/agent-icons";
import { defaultOpenGroups, ISDF_NAV, type PhaseNav } from "@/lib/isdf";
import { usePersistentState } from "@/lib/use-persistent-state";
import { cn } from "@/lib/utils";

interface AppSidebarProps {
  /** Cierra el drawer en móvil tras navegar (Bloque 4). */
  onNavigate?: () => void;
  /** En el drawer móvil se muestra siempre expandida (sin toggle de colapso). */
  forceExpanded?: boolean;
}

export function AppSidebar({ onNavigate, forceExpanded = false }: AppSidebarProps) {
  const pathname = usePathname();
  const { user, isAdmin, logout } = useAuth();
  const [collapsedPref, setCollapsed] = usePersistentState<boolean>(
    "sidebar:collapsed",
    false,
  );
  const collapsed = forceExpanded ? false : collapsedPref;
  const [openGroups, setOpenGroups] = usePersistentState<Record<string, boolean>>(
    "sidebar:groups",
    defaultOpenGroups(),
  );

  const toggleGroup = (key: string) =>
    setOpenGroups((prev) => ({ ...prev, [key]: !(prev[key] ?? false) }));

  // Atajo Ctrl+B para colapsar/expandir (solo en la sidebar de escritorio).
  useEffect(() => {
    if (forceExpanded) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.ctrlKey && (e.key === "b" || e.key === "B")) {
        e.preventDefault();
        setCollapsed((c) => !c);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [forceExpanded, setCollapsed]);

  return (
    <aside
      data-collapsed={collapsed}
      className={cn(
        "flex h-full shrink-0 flex-col border-r bg-sidebar text-sidebar-foreground transition-[width] duration-200 ease-out",
        collapsed ? "w-16" : "w-64",
      )}
    >
      {/* Cabecera de marca (degradado violeta Urbano) + toggle de colapso */}
      <div
        className={cn(
          "brand-gradient flex items-center gap-2 px-3 py-3.5",
          collapsed && "flex-col gap-2 px-0",
        )}
      >
        <Link
          href="/"
          onClick={onNavigate}
          className="flex min-w-0 items-center gap-2.5"
          title="TMS AI Studio"
        >
          {collapsed ? (
            <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-white/15 font-heading text-lg font-bold text-white ring-1 ring-white/30">
              Ü
            </span>
          ) : (
            <>
              <Image
                src="/logo-urbano.png"
                alt="Urbano"
                width={32}
                height={32}
                priority
                className="rounded-md ring-1 ring-white/30"
              />
              <span className="min-w-0 leading-tight text-white">
                <span className="block font-heading text-sm font-semibold">
                  TMS AI Studio
                </span>
                <span className="block text-[11px] text-white/85">
                  ISDF · Urbano TI
                </span>
              </span>
            </>
          )}
        </Link>

        {!forceExpanded && (
          <button
            type="button"
            onClick={() => setCollapsed((c) => !c)}
            title={collapsed ? "Expandir menú (Ctrl+B)" : "Colapsar menú (Ctrl+B)"}
            aria-label={collapsed ? "Expandir menú" : "Colapsar menú"}
            className={cn(
              "rounded-md p-1.5 text-white/80 transition-colors hover:bg-white/15 hover:text-white",
              !collapsed && "ml-auto",
            )}
          >
            {collapsed ? (
              <PanelLeftOpen className="h-4 w-4" />
            ) : (
              <PanelLeftClose className="h-4 w-4" />
            )}
          </button>
        )}
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

        {/* Configuración (solo admin) */}
        {isAdmin && (
          <ConfigSection
            collapsed={collapsed}
            pathname={pathname}
            onNavigate={onNavigate}
          />
        )}
      </nav>

      {/* Usuario actual + cerrar sesión */}
      <UserFooter
        user={user}
        collapsed={collapsed}
        onLogout={() => {
          onNavigate?.();
          logout();
        }}
      />
    </aside>
  );
}

interface ConfigSectionProps {
  collapsed: boolean;
  pathname: string;
  onNavigate?: () => void;
}

/** Sección "Configuración" con el enlace al panel de usuarios (solo admin). */
function ConfigSection({ collapsed, pathname, onNavigate }: ConfigSectionProps) {
  const href = "/configuracion/usuarios";
  const active = pathname.startsWith("/configuracion");
  return (
    <div className="mt-1 border-t border-sidebar-border/60 pt-2">
      {!collapsed && (
        <div className="px-2 py-1.5 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground/80">
          Configuración
        </div>
      )}
      <Link
        href={href}
        onClick={onNavigate}
        title={collapsed ? "Usuarios" : undefined}
        aria-current={active ? "page" : undefined}
        className={cn(
          "flex items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors",
          collapsed && "justify-center px-0",
          active
            ? "bg-sidebar-accent font-semibold text-sidebar-accent-foreground"
            : "text-sidebar-foreground/80 hover:bg-sidebar-accent/50 hover:text-sidebar-accent-foreground",
        )}
      >
        <Users className={cn("h-4 w-4 shrink-0", active && "text-primary")} />
        {!collapsed && <span className="flex-1">Usuarios</span>}
      </Link>
    </div>
  );
}

interface UserFooterProps {
  user: { full_name: string; email: string; role: "admin" | "member" } | null;
  collapsed: boolean;
  onLogout: () => void;
}

/** Pie de la sidebar: identidad del usuario (nombre + rol) y cerrar sesión. */
function UserFooter({ user, collapsed, onLogout }: UserFooterProps) {
  if (!user) return null;
  const initials = user.full_name
    .split(/\s+/)
    .slice(0, 2)
    .map((p) => p.charAt(0).toUpperCase())
    .join("");
  const roleLabel = user.role === "admin" ? "Administrador" : "Miembro";

  if (collapsed) {
    return (
      <div className="border-t p-2">
        <button
          type="button"
          onClick={onLogout}
          title={`${user.full_name} · Cerrar sesión`}
          aria-label="Cerrar sesión"
          className="flex w-full items-center justify-center rounded-md px-2 py-2 text-muted-foreground transition-colors hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground"
        >
          <LogOut className="h-4 w-4" />
        </button>
      </div>
    );
  }

  return (
    <div className="border-t p-2">
      <div className="flex items-center gap-2 rounded-md px-2 py-1.5">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary ring-1 ring-primary/20">
          {initials || "?"}
        </div>
        <div className="min-w-0 flex-1 leading-tight">
          <div className="truncate text-sm font-medium" title={user.full_name}>
            {user.full_name}
          </div>
          <div className="truncate text-[11px] text-muted-foreground" title={user.email}>
            {roleLabel}
          </div>
        </div>
      </div>
      <button
        type="button"
        onClick={onLogout}
        className="mt-1 flex w-full items-center gap-2 rounded-md px-2 py-2 text-xs font-medium text-muted-foreground transition-colors hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground"
      >
        <LogOut className="h-4 w-4" />
        <span>Cerrar sesión</span>
      </button>
    </div>
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
