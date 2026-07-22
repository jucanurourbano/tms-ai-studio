"use client";

import { useEffect, useState } from "react";

import { cn } from "@/lib/utils";

// Contador de ids estable (evita Math.random para ids deterministas por instancia).
let _idSeq = 0;

/**
 * Renderiza un diagrama Mermaid en el cliente.
 *
 * `mermaid` se importa de forma **dinámica dentro del efecto**, de modo que la
 * librería solo se descarga cuando este componente se monta. La vista del
 * artefacto de Arquitectura, además, lo carga con `next/dynamic` (`ssr:false`),
 * por lo que Mermaid **no entra en el bundle global** de la app.
 *
 * Seguridad: `securityLevel:'strict'` hace que Mermaid sanitice el contenido; el
 * SVG resultante se inserta como HTML. Si el parseo falla, se muestra el código
 * fuente como *fallback* (nunca se rompe la vista).
 */
export function MermaidDiagram({
  code,
  className,
}: {
  code: string;
  className?: string;
}) {
  const [svg, setSvg] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function render() {
      try {
        const mermaid = (await import("mermaid")).default;
        const dark =
          document.documentElement.classList.contains("dark") ||
          window.matchMedia?.("(prefers-color-scheme: dark)").matches === true;
        mermaid.initialize({
          startOnLoad: false,
          securityLevel: "strict",
          theme: dark ? "dark" : "default",
          fontFamily: "inherit",
        });
        _idSeq += 1;
        const { svg: out } = await mermaid.render(`mermaid-${_idSeq}`, code);
        if (!cancelled) {
          setSvg(out);
          setFailed(false);
        }
      } catch {
        if (!cancelled) {
          setSvg(null);
          setFailed(true);
        }
      }
    }

    void render();
    return () => {
      cancelled = true;
    };
  }, [code]);

  if (failed) {
    return (
      <pre
        className={cn(
          "overflow-x-auto rounded-lg border bg-muted/40 p-3 font-mono text-xs",
          className,
        )}
      >
        {code}
      </pre>
    );
  }

  if (svg === null) {
    return (
      <div
        aria-hidden
        className={cn("h-40 animate-pulse rounded-lg bg-muted/40", className)}
      />
    );
  }

  return (
    <div
      className={cn(
        "mermaid-diagram overflow-x-auto rounded-lg border bg-card p-3 [&_svg]:mx-auto [&_svg]:h-auto [&_svg]:max-w-full",
        className,
      )}
      // SVG generado por Mermaid con securityLevel 'strict' (contenido sanitizado).
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}
