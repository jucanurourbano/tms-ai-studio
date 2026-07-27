"use client";

// Estado del CENTRO DE COMANDO de un artefacto.
//
// La página del job es un hub de tarjetas y TODO el contenido se explora en un
// único panel lateral. Este hook es la máquina de estados de ese panel:
//
//   · qué sección está abierta (y en qué sub-pestaña),
//   · el mini-historial de navegación (saltar por un chip de referencia y volver,
//     como el botón atrás de un navegador),
//   · el deep-link por hash (`#preguntas`) para que compartir el enlace abra el
//     job con ese panel ya abierto,
//   · el ancho del panel (persistido) y los atajos de teclado.
//
// El historial SOLO crece con los saltos por referencia. Cambiar de sección con
// el switcher reinicia la pila: es un destino nuevo, no un paso atrás.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { usePersistentState } from "@/lib/use-persistent-state";

/** Un paso del historial del panel. */
export interface HubNavEntry {
  sectionId: string;
  tabId?: string;
  /** Referencia a resaltar al abrir (salto desde un chip). */
  refId?: string;
}

/** Ancho por defecto del panel: media pantalla. */
const DEFAULT_WIDTH = 50;
/** Límites del arrastre: nunca tan estrecho que no quepa una fila, ni tapando el hub. */
export const MIN_WIDTH = 40;
export const MAX_WIDTH = 85;
/** Ancho del botón "expandir". */
const WIDE_WIDTH = 70;

export function useArtifactHub(sectionIds: readonly string[]) {
  const [stack, setStack] = useState<HubNavEntry[]>([]);
  const [width, setWidth] = usePersistentState(
    "artifact:panel-width",
    DEFAULT_WIDTH,
  );

  const key = sectionIds.join(",");
  const ids = useMemo(
    () => [...sectionIds],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [key],
  );

  const open = stack.length > 0;
  const current = open ? stack[stack.length - 1] : null;
  const canGoBack = stack.length > 1;

  /** Abre una sección desde el hub (o desde el switcher): historial nuevo. */
  const openSection = useCallback((sectionId: string, tabId?: string) => {
    setStack([{ sectionId, tabId }]);
  }, []);

  /** Salto por referencia: apila para poder volver al panel de origen. */
  const pushEntry = useCallback((entry: HubNavEntry) => {
    setStack((prev) => {
      // Tope de historial: 12 pasos bastan para cualquier cadena de saltos y
      // evitan que una sesión larga acumule estado sin fin.
      const next = [...prev, entry];
      return next.length > 12 ? next.slice(next.length - 12) : next;
    });
  }, []);

  const back = useCallback(() => {
    setStack((prev) => (prev.length > 1 ? prev.slice(0, -1) : prev));
  }, []);

  const close = useCallback(() => setStack([]), []);

  /** Cambia de sub-pestaña sin tocar el historial. */
  const setTab = useCallback((tabId: string) => {
    setStack((prev) => {
      if (prev.length === 0) return prev;
      const next = [...prev];
      next[next.length - 1] = { ...next[next.length - 1], tabId, refId: undefined };
      return next;
    });
  }, []);

  /** Sección anterior/siguiente (switcher y flechas del teclado). */
  const step = useCallback(
    (delta: number) => {
      setStack((prev) => {
        if (prev.length === 0) return prev;
        const currentId = prev[prev.length - 1].sectionId;
        const i = ids.indexOf(currentId);
        if (i === -1) return prev;
        const next = (i + delta + ids.length) % ids.length;
        return [{ sectionId: ids[next] }];
      });
    },
    [ids],
  );

  const goPrev = useCallback(() => step(-1), [step]);
  const goNext = useCallback(() => step(1), [step]);

  const expand = useCallback(
    () => setWidth((w) => (w >= WIDE_WIDTH ? DEFAULT_WIDTH : WIDE_WIDTH)),
    [setWidth],
  );
  const resize = useCallback(
    (pct: number) =>
      setWidth(Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, Math.round(pct)))),
    [setWidth],
  );

  // --- deep-linking por hash -------------------------------------------------

  // Apertura inicial: si la URL trae `#seccion`, el panel nace abierto ahí.
  // La lectura se aplaza a un microtask (fuera del cuerpo síncrono del efecto)
  // para no encadenar renders y para no depender de `window` en el render.
  const hydrated = useRef(false);
  useEffect(() => {
    if (hydrated.current) return;
    let cancelled = false;
    Promise.resolve().then(() => {
      if (cancelled || hydrated.current) return;
      hydrated.current = true;
      const slug = window.location.hash.replace(/^#/, "");
      if (!slug) return;
      const [sectionId, tabId] = slug.split("/");
      if (ids.includes(sectionId)) setStack([{ sectionId, tabId }]);
    });
    return () => {
      cancelled = true;
    };
  }, [ids]);

  // La URL sigue al panel: compartirla reproduce el estado (sección + pestaña).
  const currentId = current?.sectionId;
  const currentTab = current?.tabId;
  useEffect(() => {
    if (!hydrated.current) return;
    const base = window.location.pathname + window.location.search;
    const hash = currentId
      ? `#${currentId}${currentTab ? `/${currentTab}` : ""}`
      : "";
    // `replaceState` y no `hash =`: cambiar el hash directamente empuja una
    // entrada al historial del navegador y desplazaría al elemento homónimo.
    window.history.replaceState(null, "", base + hash);
  }, [currentId, currentTab]);

  // --- atajos de teclado ----------------------------------------------------

  // ←/→ cambian de sección sin volver al hub. Se ignoran mientras se escribe
  // (buscador local, respuesta a una pregunta) para no secuestrar el cursor.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const el = e.target as HTMLElement | null;
      const tag = el?.tagName;
      if (
        tag === "INPUT" ||
        tag === "TEXTAREA" ||
        tag === "SELECT" ||
        el?.isContentEditable
      ) {
        return;
      }
      e.preventDefault();
      if (e.key === "ArrowLeft") goPrev();
      else goNext();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, goPrev, goNext]);

  return {
    open,
    current,
    canGoBack,
    openSection,
    pushEntry,
    back,
    close,
    setTab,
    goPrev,
    goNext,
    width,
    expand,
    resize,
    isWide: width >= WIDE_WIDTH,
  };
}

export type ArtifactHub = ReturnType<typeof useArtifactHub>;
