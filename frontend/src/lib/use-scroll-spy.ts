"use client";

import { useEffect, useState } from "react";

/**
 * Scrollspy: observa las secciones (por id) dentro de un contenedor scrolleable
 * y devuelve el id de la sección "activa" (la superior visible bajo la cabecera).
 *
 * @param ids  ids de las secciones, en orden de aparición (memoizar en el consumidor).
 * @param scrollRootId  id del contenedor con overflow (por defecto el `main` global).
 */
export function useScrollSpy(
  ids: string[],
  scrollRootId = "app-scroll",
): string | null {
  const [active, setActive] = useState<string | null>(ids[0] ?? null);
  const key = ids.join(",");

  useEffect(() => {
    const root = document.getElementById(scrollRootId);
    const els = ids
      .map((id) => document.getElementById(id))
      .filter((el): el is HTMLElement => el != null);
    if (els.length === 0) return;

    const visible = new Set<string>();
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) visible.add(entry.target.id);
          else visible.delete(entry.target.id);
        }
        const topmost = ids.find((id) => visible.has(id));
        if (topmost) setActive(topmost);
      },
      {
        root,
        // Bajo la cabecera sticky (~96px); activa cuando entra en el 40% superior.
        rootMargin: "-96px 0px -55% 0px",
        threshold: [0, 1],
      },
    );
    els.forEach((el) => observer.observe(el));
    return () => observer.disconnect();
    // key resume el contenido de ids sin depender de su identidad de array.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, scrollRootId]);

  return active;
}
