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

  const printNow = useCallback(() => {
    setPrintMode(true);
    // Doble rAF: garantiza que React montó/expandió todo antes de imprimir.
    requestAnimationFrame(() =>
      requestAnimationFrame(() => {
        window.print();
      }),
    );
  }, []);

  return { printMode, printNow };
}
