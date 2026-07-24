"use client";

import { useEffect, useRef, useState } from "react";

/**
 * Devuelve `true` de forma efímera cuando `value` pasa de false→true, para
 * disparar UNA celebración discreta (p. ej. el semáforo al ponerse verde).
 *
 * La línea base se fija en el primer estado ya cargado (`active`), de modo que
 * abrir un artefacto que YA está en verde no dispara la celebración: solo la
 * dispara la transición provocada por el usuario durante el afinamiento.
 */
export function useCelebrateOnTrue(value: boolean, active = true, ms = 1100) {
  const baselineSet = useRef(false);
  const prev = useRef(false);
  const [celebrate, setCelebrate] = useState(false);

  useEffect(() => {
    if (!active) return;
    if (!baselineSet.current) {
      baselineSet.current = true;
      prev.current = value;
      return;
    }
    if (value && !prev.current) {
      prev.current = value;
      setCelebrate(true);
      const t = setTimeout(() => setCelebrate(false), ms);
      return () => clearTimeout(t);
    }
    prev.current = value;
  }, [value, active, ms]);

  return celebrate;
}
