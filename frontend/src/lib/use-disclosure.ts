"use client";

import { useCallback, useState } from "react";

/**
 * Estado de revelación progresiva de las secciones de un artefacto.
 *
 * Principio: al abrir el job todo está colapsado (vista resumen). El usuario abre
 * una sección a la vez; se permite un máximo (`maxOpen`, por defecto 2) abiertas
 * simultáneamente — al superarlo se cierra la que se abrió hace más tiempo. El
 * salto desde el índice usa `openOnly`, que abre una y colapsa el resto.
 *
 * El orden de apertura se mantiene para desalojar la más antigua (FIFO).
 */
export function useDisclosure(maxOpen = 2) {
  // Lista ordenada por momento de apertura (la primera es la más antigua).
  const [openList, setOpenList] = useState<string[]>([]);

  const isOpen = useCallback((id: string) => openList.includes(id), [openList]);

  const toggle = useCallback(
    (id: string) => {
      setOpenList((prev) => {
        if (prev.includes(id)) return prev.filter((x) => x !== id);
        const next = [...prev, id];
        // Desaloja las más antiguas hasta respetar el máximo.
        while (next.length > maxOpen) next.shift();
        return next;
      });
    },
    [maxOpen],
  );

  /** Abre exactamente una sección y colapsa las demás (salto desde el índice). */
  const openOnly = useCallback((id: string) => {
    setOpenList([id]);
  }, []);

  const collapseAll = useCallback(() => setOpenList([]), []);

  return { isOpen, toggle, openOnly, collapseAll, openIds: openList };
}
