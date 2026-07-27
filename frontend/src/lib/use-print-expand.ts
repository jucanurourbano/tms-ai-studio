"use client";

import { useCallback, useEffect, useState } from "react";

/**
 * Coordina la impresión con la revelación progresiva: como las secciones
 * colapsadas NO montan su contenido (lazy render), antes de imprimir hay que
 * forzar el montaje de todo el artefacto.
 *
 * `printMode` (cuando es true) hace que cada `ArtifactSection` renderice y
 * expanda su contenido para el PDF. `printNow` lo activa, espera al paint y
 * lanza `window.print()`. También se escucha `beforeprint`/`afterprint` para
 * cubrir el Ctrl+P del navegador.
 */
export function usePrintExpand() {
  const [printMode, setPrintMode] = useState(false);

  useEffect(() => {
    const before = () => setPrintMode(true);
    const after = () => setPrintMode(false);
    window.addEventListener("beforeprint", before);
    window.addEventListener("afterprint", after);
    return () => {
      window.removeEventListener("beforeprint", before);
      window.removeEventListener("afterprint", after);
    };
  }, []);

  /**
   * Activa el modo impresión y lanza el diálogo cuando el documento está listo.
   *
   * `isReady` permite esperar contenido ASÍNCRONO: los diagramas Mermaid de
   * Arquitectura se generan tras cargar la librería, y sin esperarlos el PDF
   * saldría con los huecos vacíos. Si no llegan en `timeoutMs` se imprime igual
   * (mejor un informe sin un diagrama que un botón que no responde).
   *
   * El Ctrl+P del navegador no puede esperar a nada: ahí solo actúa
   * `beforeprint`, que monta el documento pero imprime de inmediato.
   */
  const printNow = useCallback(
    (isReady?: () => boolean, timeoutMs = 5000) => {
      setPrintMode(true);
      const started = performance.now();
      const tick = () => {
        if (!isReady || isReady() || performance.now() - started > timeoutMs) {
          window.print();
          return;
        }
        requestAnimationFrame(tick);
      };
      // Doble rAF: garantiza que React montó/expandió todo antes de comprobar.
      requestAnimationFrame(() => requestAnimationFrame(tick));
    },
    [],
  );

  return { printMode, printNow };
}
