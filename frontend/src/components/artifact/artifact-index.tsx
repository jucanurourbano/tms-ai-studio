"use client";

import { ChevronRight, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { useMemo, useState } from "react";

import { useScrollSpy } from "@/lib/use-scroll-spy";
import { cn } from "@/lib/utils";

export interface IndexChild {
  id: string;
  label: string;
  count?: number;
}

export interface IndexSection {
  /** id del elemento destino (sin `#`). */
  id: string;
  label: string;
  count?: number;
  /** Texto auxiliar a la derecha (p. ej. "3 bloq."). */
  meta?: string;
  /** Sub-ítems plegables (p. ej. las dimensiones del Modelo). */
  children?: IndexChild[];
}

/** Conteo con estado vacío EXPLÍCITO (nunca oculto). */
function Count({ n }: { n?: number }) {
  if (n === undefined) return null;
  if (n === 0) return <span className="text-amber-600">0 ⚠</span>;
  return <span className="text-foreground/80">{n}</span>;
}

/**
 * Índice navegable del artefacto: anclas clicables con scroll suave (vía
 * `scroll-smooth` + `scroll-mt` en las secciones), scrollspy que resalta la
 * sección visible, y sub-grupo plegable. Compartido por EF y Scrum.
 */
export function ArtifactIndex({
  sections,
  scrollRootId = "app-scroll",
  hideDesktopNav = false,
}: {
  sections: IndexSection[];
  scrollRootId?: string;
  /** Oculta el índice de escritorio (modo colapsado); el select móvil se mantiene. */
  hideDesktopNav?: boolean;
}) {
  const key = sections.map((s) => s.id).join(",");
  const ids = useMemo(
    () => sections.flatMap((s) => [s.id, ...(s.children?.map((c) => c.id) ?? [])]),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [key],
  );
  const active = useScrollSpy(ids, scrollRootId);
  const [openSubs, setOpenSubs] = useState<Record<string, boolean>>({});

  const isOpen = (id: string, fallback: boolean) => openSubs[id] ?? fallback;

  const jumpTo = (id: string) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "start" });
    history.replaceState(null, "", `#${id}`);
  };

  return (
    <>
      {/* Móvil: selector de navegación (el índice lateral se oculta) */}
      <div className="mb-4 md:hidden">
        <label htmlFor="artifact-nav" className="sr-only">
          Ir a la sección
        </label>
        <select
          id="artifact-nav"
          value={active ?? sections[0]?.id ?? ""}
          onChange={(e) => jumpTo(e.target.value)}
          className="w-full rounded-md border bg-background px-3 py-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {sections.map((s) => (
            <optgroup key={s.id} label={s.label}>
              <option value={s.id}>
                {s.label}
                {s.count !== undefined ? ` (${s.count})` : ""}
              </option>
              {s.children?.map((c) => (
                <option key={c.id} value={c.id}>
                  {"  "}
                  {c.label}
                  {c.count !== undefined ? ` (${c.count})` : ""}
                </option>
              ))}
            </optgroup>
          ))}
        </select>
      </div>

      {/* Escritorio: índice lateral navegable con scrollspy */}
      <nav
        aria-label="Índice del artefacto"
        className={cn(
          "space-y-1 text-sm",
          hideDesktopNav ? "hidden" : "hidden md:block",
        )}
      >
      {sections.map((section) => {
        const childActive = section.children?.some((c) => c.id === active);
        const parentActive = active === section.id || childActive;
        const hasChildren = !!section.children?.length;
        const open = isOpen(section.id, true);

        return (
          <div key={section.id}>
            <div
              className={cn(
                "flex items-center gap-1 rounded-md pr-1 transition-colors",
                parentActive && "bg-accent/60",
              )}
            >
              <a
                href={`#${section.id}`}
                className={cn(
                  "flex flex-1 items-center justify-between gap-2 rounded-md px-2 py-1.5 font-medium transition-colors hover:text-primary",
                  parentActive ? "text-primary" : "text-foreground/80",
                )}
              >
                <span className="flex items-center gap-2">
                  <span
                    className={cn(
                      "h-3.5 w-0.5 rounded-full transition-colors",
                      parentActive ? "bg-primary" : "bg-transparent",
                    )}
                  />
                  {section.label}
                </span>
                <span className="flex items-center gap-2 text-xs">
                  <Count n={section.count} />
                  {section.meta && (
                    <span className="text-muted-foreground">{section.meta}</span>
                  )}
                </span>
              </a>
              {hasChildren && (
                <button
                  type="button"
                  onClick={() =>
                    setOpenSubs((prev) => ({ ...prev, [section.id]: !open }))
                  }
                  aria-expanded={open}
                  aria-label={open ? "Plegar sub-índice" : "Desplegar sub-índice"}
                  className="rounded p-0.5 text-muted-foreground hover:text-foreground"
                >
                  <ChevronRight
                    className={cn(
                      "h-3.5 w-3.5 transition-transform duration-200",
                      open && "rotate-90",
                    )}
                  />
                </button>
              )}
            </div>

            {hasChildren && (
              <div
                className={cn(
                  "grid transition-[grid-template-rows] duration-200 ease-in-out",
                  open ? "grid-rows-[1fr]" : "grid-rows-[0fr]",
                )}
              >
                <ul className="overflow-hidden pl-3">
                  {section.children!.map((child) => (
                    <li key={child.id}>
                      <a
                        href={`#${child.id}`}
                        className={cn(
                          "flex items-center justify-between gap-2 rounded-md px-2 py-1 text-xs transition-colors hover:text-primary",
                          active === child.id
                            ? "font-medium text-primary"
                            : "text-muted-foreground",
                        )}
                      >
                        <span>{child.label}</span>
                        <Count n={child.count} />
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        );
      })}
      </nav>
    </>
  );
}

/**
 * Índice con cabecera y botón icónico de colapso (mismo lenguaje visual que el
 * sidebar). Colapsado deja el contenido a ancho completo; el estado lo gestiona
 * (y persiste) la vista de artefacto. En móvil siempre se muestra el select.
 */
export function ArtifactIndexPanel({
  sections,
  collapsed,
  onToggle,
  scrollRootId,
}: {
  sections: IndexSection[];
  collapsed: boolean;
  onToggle: () => void;
  scrollRootId?: string;
}) {
  return (
    <div>
      {/* Cabecera del índice (solo escritorio) */}
      <div
        className={cn(
          "mb-2 hidden md:flex",
          collapsed ? "md:justify-center" : "md:items-center md:justify-between",
        )}
      >
        {!collapsed && (
          <span className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground/80">
            Índice
          </span>
        )}
        <button
          type="button"
          onClick={onToggle}
          title={collapsed ? "Mostrar índice" : "Ocultar índice"}
          aria-label={collapsed ? "Mostrar índice" : "Ocultar índice"}
          className="rounded-md border bg-card p-1.5 text-muted-foreground shadow-sm transition-colors hover:border-primary/40 hover:text-primary"
        >
          {collapsed ? (
            <PanelLeftOpen className="h-4 w-4" />
          ) : (
            <PanelLeftClose className="h-4 w-4" />
          )}
        </button>
      </div>
      <ArtifactIndex
        sections={sections}
        scrollRootId={scrollRootId}
        hideDesktopNav={collapsed}
      />
    </div>
  );
}
