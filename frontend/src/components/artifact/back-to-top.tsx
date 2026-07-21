"use client";

import { ArrowUp } from "lucide-react";
import { useEffect, useState } from "react";

/** Botón flotante "volver arriba": aparece al superar ~una pantalla de scroll. */
export function BackToTop({ scrollRootId = "app-scroll" }: { scrollRootId?: string }) {
  const [show, setShow] = useState(false);

  useEffect(() => {
    const root = document.getElementById(scrollRootId);
    if (!root) return;
    const onScroll = () => setShow(root.scrollTop > window.innerHeight * 0.8);
    root.addEventListener("scroll", onScroll, { passive: true });
    return () => root.removeEventListener("scroll", onScroll);
  }, [scrollRootId]);

  if (!show) return null;

  return (
    <button
      type="button"
      onClick={() =>
        document
          .getElementById(scrollRootId)
          ?.scrollTo({ top: 0, behavior: "smooth" })
      }
      aria-label="Volver arriba"
      title="Volver arriba"
      className="fixed bottom-6 right-6 z-30 flex h-10 w-10 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-lg ring-1 ring-black/5 transition-all hover:brightness-110 hover:shadow-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <ArrowUp className="h-5 w-5" />
    </button>
  );
}
