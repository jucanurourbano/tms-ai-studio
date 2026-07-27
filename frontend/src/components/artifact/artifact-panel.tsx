"use client";

// EL PANEL LATERAL UNIVERSAL — la estrella del centro de comando.
//
// Todo el contenido de un artefacto se explora aquí: media pantalla desde la
// derecha, el hub visible pero atenuado detrás. Un solo componente para las tres
// vistas (EF, Scrum, Arquitectura) y para cualquier agente futuro, porque las
// secciones entran como DATOS (`HubSection[]`), no como JSX incrustado.
//
// La cabecera es fija y concentra la navegación: volver (mini-historial de
// saltos por referencia), icono + título + conteo, buscador local, switcher de
// sección (◂ ▸ + selector), ancho y cerrar. Debajo, sub-pestañas cuando la
// sección las tiene; el cuerpo tiene su propio scroll.
//
// El contenido de cada sección se declara una sola vez y se reutiliza en el
// documento imprimible (ver `ArtifactPrintDoc`): el PDF NO usa paneles, así que
// el mismo `render` se invoca con `forPrint: true` y sin filtro de búsqueda.

import {
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  Maximize2,
  Minimize2,
  Search,
  X,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { CountChip } from "@/components/artifact/primitives";
import { Button } from "@/components/ui/button";
import { NativeSelect } from "@/components/ui/native-select";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  toneOf,
  type SectionPattern,
  type SectionTone,
} from "@/lib/card-accent";
import { accentOf } from "@/lib/module-accent";
import type { ModuleKey } from "@/lib/types/auth";
import type { ArtifactHub } from "@/lib/use-artifact-hub";
import { MAX_WIDTH, MIN_WIDTH } from "@/lib/use-artifact-hub";
import { cn } from "@/lib/utils";

/** Contexto con el que se pinta el contenido de una sección. */
export interface PanelRenderCtx {
  /** Texto del buscador local; vacío = sin filtro. */
  query: string;
  /** true al construir el documento imprimible (sin filtros ni controles). */
  forPrint: boolean;
  /**
   * Referencia a la que se acaba de saltar, si la hay. La sección puede usarla
   * para desplegar el detalle que la contiene (un criterio de aceptación vive
   * dentro de su historia y, plegado, no habría nada que resaltar).
   */
  refId?: string;
}

export interface PanelTab {
  id: string;
  label: string;
  count?: number;
  /**
   * Cuántos ítems encajan con la búsqueda. Cuando se declara, al escribir en el
   * buscador las pestañas muestran las COINCIDENCIAS en vez del total: así se ve
   * de un golpe en qué pestaña está lo que se busca, sin ir tanteando una a una.
   */
  matchCount?: (query: string) => number;
  /**
   * La pestaña es una VISTA FILTRADA de otra (p. ej. "Must" sobre "Todas") y por
   * tanto no aporta contenido nuevo al PDF: incluirla duplicaría las mismas
   * historias en el informe.
   */
  printSkip?: boolean;
  render: (ctx: PanelRenderCtx) => React.ReactNode;
}

/**
 * Una sección del artefacto: tarjeta en el hub, panel al abrirla y capítulo del
 * PDF. Con `tabs` el panel muestra sub-pestañas; con `render`, contenido único.
 */
export interface HubSection {
  /** Slug estable: identifica la sección en el hash (`#preguntas`). */
  id: string;
  title: string;
  /** Título del capítulo en el PDF, si difiere del de la tarjeta. */
  printTitle?: string;
  icon: React.ReactNode;
  count?: number;
  /** Tono propio de la sección: tiñe su tarjeta, su icono y su pill activa. */
  tone?: SectionTone;
  /** Textura de fondo de la tarjeta (solo si dice algo de la sección). */
  pattern?: SectionPattern;
  /** Cifra protagonista de la tarjeta y su etiqueta. */
  stat?: { value: React.ReactNode; label: string };
  /** Alternativa a `stat` cuando la sección no se resume en un número. */
  metrics?: React.ReactNode;
  /** Línea de insight de la tarjeta. */
  insight?: React.ReactNode;
  urgent?: boolean;
  urgentLabel?: string;
  /** Controles propios en la cabecera del panel (filtros, toggles). */
  actions?: React.ReactNode;
  /** El buscador local se muestra salvo que la sección sea prosa sin listas. */
  searchable?: boolean;
  tabs?: PanelTab[];
  render?: (ctx: PanelRenderCtx) => React.ReactNode;
}

export function ArtifactPanel({
  hub,
  sections,
  module,
}: {
  hub: ArtifactHub;
  sections: HubSection[];
  module: ModuleKey;
}) {
  const current = hub.current;
  const section = current
    ? sections.find((s) => s.id === current.sectionId)
    : undefined;
  const panelRef = useRef<HTMLDivElement>(null);

  return (
    <Sheet open={hub.open} onOpenChange={(o) => !o && hub.close()}>
      <SheetContent
        ref={panelRef}
        tabIndex={-1}
        // El foco entra en el PANEL, no en el primer control. Por defecto caía en
        // el selector de sección, y ahí una flecha del teclado cambiaba de
        // sección sin que nadie lo pidiera.
        initialFocus={panelRef}
        showCloseButton={false}
        aria-describedby={undefined}
        className="max-w-none md:w-[var(--panel-w)]"
        style={{ "--panel-w": `${hub.width}%` } as React.CSSProperties}
      >
        <ResizeHandle onResize={hub.resize} />
        {section && current ? (
          // El `key` incluye la pestaña a propósito: remontar al cambiar de
          // sección o de sub-pestaña limpia el buscador local y el scroll sin
          // necesidad de sincronizarlos con efectos.
          <PanelInner
            key={`${section.id}/${current.tabId ?? ""}`}
            hub={hub}
            sections={sections}
            section={section}
            module={module}
            tabId={current.tabId}
            refId={current.refId}
          />
        ) : (
          <SheetHeader>
            <SheetTitle>Sección no disponible</SheetTitle>
          </SheetHeader>
        )}
      </SheetContent>
    </Sheet>
  );
}

function PanelInner({
  hub,
  sections,
  section,
  module,
  tabId,
  refId,
}: {
  hub: ArtifactHub;
  sections: HubSection[];
  section: HubSection;
  module: ModuleKey;
  tabId?: string;
  refId?: string;
}) {
  const [query, setQuery] = useState("");
  const bodyRef = useRef<HTMLDivElement>(null);
  // La identidad de la sección viaja de la tarjeta al panel: el mismo tono
  // tiñe el icono de la cabecera y la pill activa. Sin tono propio, manda el
  // acento del módulo.
  const accent = section.tone ? toneOf(section.tone) : accentOf(module);

  const tabs = section.tabs;
  const activeTab = tabs
    ? (tabs.find((t) => t.id === tabId) ?? tabs[0])
    : undefined;
  const searchable = section.searchable ?? true;

  // Salto por referencia: desplaza y resalta la fila dentro del panel. Si el id
  // no está montado (filtrado, o el artefacto no lo contiene) se avisa en vez de
  // dejar al usuario mirando una lista que no cambió.
  useEffect(() => {
    if (!refId) return;
    const raf = requestAnimationFrame(() => {
      const el = bodyRef.current?.querySelector<HTMLElement>(
        `[id="ref-${refId}"]`,
      );
      if (!el) {
        toast.info(`Referencia ${refId} no encontrada en esta sección.`);
        return;
      }
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      el.classList.add("ref-highlight");
      window.setTimeout(() => el.classList.remove("ref-highlight"), 1600);
    });
    return () => cancelAnimationFrame(raf);
  }, [refId, section.id, activeTab?.id]);

  const count = activeTab?.count ?? section.count;

  return (
    <>
      <SheetHeader className="gap-2">
        <div className="flex items-center gap-2">
          {hub.canGoBack && (
            <Button
              variant="ghost"
              size="sm"
              className="-ml-1.5 h-7 gap-1 px-1.5 text-xs"
              onClick={hub.back}
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              volver
            </Button>
          )}
          {/* En móvil el icono cede su sitio: la cabecera tiene que caber en
              390px con el título, el selector de sección y el cierre. */}
          <span
            className={cn(
              "hidden h-7 w-7 shrink-0 items-center justify-center rounded-md sm:flex [&_svg]:h-4 [&_svg]:w-4",
              accent.soft,
            )}
            aria-hidden
          >
            {section.icon}
          </span>
          <SheetTitle className="min-w-0 truncate">{section.title}</SheetTitle>
          {count !== undefined && <CountChip n={count} />}

          <div className="ml-auto flex items-center gap-0.5">
            <SectionSwitcher hub={hub} sections={sections} current={section.id} />
            <Button
              variant="ghost"
              size="icon-sm"
              className="hidden md:inline-flex"
              onClick={hub.expand}
              title={hub.isWide ? "Reducir el panel" : "Ampliar el panel"}
              aria-label={hub.isWide ? "Reducir el panel" : "Ampliar el panel"}
            >
              {hub.isWide ? <Minimize2 /> : <Maximize2 />}
            </Button>
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={hub.close}
              title="Cerrar (Esc)"
              aria-label="Cerrar el panel"
            >
              <X />
            </Button>
          </div>
        </div>

        {(searchable || section.actions) && (
          <div className="flex flex-wrap items-center gap-2">
            {searchable && (
              <div className="relative min-w-0 flex-1">
                <Search className="pointer-events-none absolute top-1/2 left-2.5 h-3.5 w-3.5 -translate-y-1/2 text-meta-foreground" />
                <input
                  type="search"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder={`Buscar en ${section.title.toLowerCase()}…`}
                  aria-label={`Buscar en ${section.title}`}
                  className="field-base pl-8 text-xs"
                />
              </div>
            )}
            {section.actions}
          </div>
        )}

        {tabs && tabs.length > 0 && (
          // Sub-pestañas como PILLS QUE ENVUELVEN, no una fila con scroll.
          //
          // El Modelo del EF tiene once categorías: en una sola fila desbordaban
          // y había que arrastrar para descubrir que existían "Relaciones" o
          // "APIs". Se descartó el patrón "5 visibles + Más ▾" porque esconde
          // media sección tras un clic extra y reintroduce el mismo problema de
          // descubrimiento; con etiquetas cortas, dos filas de pills muestran
          // TODO de un vistazo y dejan ver dónde hay contenido y dónde no.
          <div
            className="flex flex-wrap gap-1.5"
            role="tablist"
            aria-label={`Secciones de ${section.title}`}
          >
            {tabs.map((t) => {
              const active = t.id === activeTab?.id;
              const searching = query.trim().length > 0 && !!t.matchCount;
              const n = searching ? t.matchCount!(query) : t.count;
              return (
                <button
                  key={t.id}
                  type="button"
                  role="tab"
                  aria-selected={active}
                  onClick={() => hub.setTab(t.id)}
                  className={cn(
                    "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs transition-colors duration-150",
                    active
                      ? cn("font-medium ring-1 ring-inset", accent.soft, accent.ring)
                      : "text-muted-foreground hover:bg-muted hover:text-foreground",
                    // Buscando: las pestañas sin coincidencias se apagan.
                    searching && n === 0 && !active && "opacity-40",
                  )}
                >
                  {t.label}
                  {n !== undefined && (
                    <span
                      className={cn(
                        "rounded-full px-1 text-[10px] tabular-nums",
                        active
                          ? "bg-background/70"
                          : n === 0 && !searching
                            ? "bg-amber-100 text-amber-700"
                            : "bg-muted text-meta-foreground",
                      )}
                    >
                      {n}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        )}
      </SheetHeader>

      {/* Cuerpo con scroll propio. El `key` hace que cambiar de sección o de
          pestaña entre con un fade corto y arranque el scroll arriba. */}
      <div
        ref={bodyRef}
        key={`${section.id}/${activeTab?.id ?? ""}`}
        className="animate-panel-fade min-h-0 flex-1 overflow-y-auto px-5 py-4"
      >
        {activeTab
          ? activeTab.render({ query, forPrint: false, refId })
          : section.render?.({ query, forPrint: false, refId })}
      </div>
    </>
  );
}

/**
 * Cambia de sección sin volver al hub (también con ←/→). En móvil solo queda el
 * selector: las flechas son un lujo de escritorio y ahí el ancho manda.
 */
function SectionSwitcher({
  hub,
  sections,
  current,
}: {
  hub: ArtifactHub;
  sections: HubSection[];
  current: string;
}) {
  return (
    <div className="flex items-center gap-0.5">
      <Button
        variant="ghost"
        size="icon-sm"
        className="hidden md:inline-flex"
        onClick={hub.goPrev}
        title="Sección anterior (←)"
        aria-label="Sección anterior"
      >
        <ChevronLeft />
      </Button>
      <NativeSelect
        value={current}
        onChange={(e) => hub.openSection(e.target.value)}
        aria-label="Ir a otra sección"
        className="max-w-[7.5rem] text-xs md:max-w-[9.5rem]"
      >
        {sections.map((s) => (
          <option key={s.id} value={s.id}>
            {s.title}
          </option>
        ))}
      </NativeSelect>
      <Button
        variant="ghost"
        size="icon-sm"
        className="hidden md:inline-flex"
        onClick={hub.goNext}
        title="Sección siguiente (→)"
        aria-label="Sección siguiente"
      >
        <ChevronRight />
      </Button>
    </div>
  );
}

/**
 * Borde arrastrable del panel (solo escritorio). El ancho se guarda en
 * localStorage, así que la preferencia sobrevive a la sesión.
 */
function ResizeHandle({ onResize }: { onResize: (pct: number) => void }) {
  const [dragging, setDragging] = useState(false);

  const onPointerDown = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragging(true);
  }, []);

  useEffect(() => {
    if (!dragging) return;
    const move = (e: PointerEvent) => {
      const pct = ((window.innerWidth - e.clientX) / window.innerWidth) * 100;
      onResize(pct);
    };
    const up = () => setDragging(false);
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    // Mientras se arrastra, el cursor manda en toda la ventana y no se
    // selecciona texto por accidente.
    const prevCursor = document.body.style.cursor;
    const prevSelect = document.body.style.userSelect;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      document.body.style.cursor = prevCursor;
      document.body.style.userSelect = prevSelect;
    };
  }, [dragging, onResize]);

  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label="Ajustar el ancho del panel"
      onPointerDown={onPointerDown}
      onKeyDown={(e) => {
        // Accesible por teclado: las flechas mueven el borde de 5 en 5.
        if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
          e.preventDefault();
          const el = e.currentTarget.parentElement;
          if (!el) return;
          const pct = (el.getBoundingClientRect().width / window.innerWidth) * 100;
          onResize(pct + (e.key === "ArrowLeft" ? 5 : -5));
        }
      }}
      tabIndex={0}
      className={cn(
        "absolute inset-y-0 left-0 z-10 hidden w-1.5 cursor-col-resize md:block",
        "after:absolute after:inset-y-0 after:left-0 after:w-px after:bg-transparent after:transition-colors hover:after:bg-primary/50 focus-visible:after:bg-primary",
        dragging && "after:bg-primary",
      )}
      title={`Arrastra para ajustar (${MIN_WIDTH}–${MAX_WIDTH}%)`}
    />
  );
}
