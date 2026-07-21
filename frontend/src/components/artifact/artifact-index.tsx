"use client";

import { ChevronRight } from "lucide-react";
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
}: {
  sections: IndexSection[];
  scrollRootId?: string;
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

  return (
    <nav aria-label="Índice del artefacto" className="space-y-1 text-sm">
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
  );
}
