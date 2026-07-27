"use client";

import { Search, X } from "lucide-react";
import { useEffect, useRef } from "react";

import { cn } from "@/lib/utils";

/**
 * Buscador estándar de la app: **lupa interna**, botón de **limpiar (×)** cuando
 * hay texto y atajo **`/`** para enfocar sin usar el ratón.
 *
 * El atajo se ignora si el foco ya está en un campo de texto (si no, escribir "/"
 * en cualquier input saltaría al buscador) y la pista visual solo se muestra
 * cuando el campo está vacío y en pantallas donde hay teclado físico.
 */
export function SearchInput({
  value,
  onChange,
  placeholder = "Buscar…",
  className,
  disabled,
  "aria-label": ariaLabel,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
  disabled?: boolean;
  "aria-label"?: string;
}) {
  const ref = useRef<HTMLInputElement>(null);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key !== "/" || e.metaKey || e.ctrlKey || e.altKey) return;
      const activo = document.activeElement;
      const escribiendo =
        activo instanceof HTMLInputElement ||
        activo instanceof HTMLTextAreaElement ||
        activo instanceof HTMLSelectElement ||
        (activo instanceof HTMLElement && activo.isContentEditable);
      if (escribiendo) return;
      e.preventDefault();
      ref.current?.focus();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className={cn("relative min-w-0 flex-1", className)}>
      <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-meta-foreground" />
      <input
        ref={ref}
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        disabled={disabled}
        aria-label={ariaLabel ?? placeholder}
        className={cn(
          "field-base w-full pl-9",
          // Sitio para el botón de limpiar o para la pista del atajo.
          "pr-9",
          // El aspa nativa del `type=search` duplicaría nuestro botón.
          "[&::-webkit-search-cancel-button]:appearance-none",
        )}
      />
      {value ? (
        <button
          type="button"
          onClick={() => {
            onChange("");
            ref.current?.focus();
          }}
          aria-label="Limpiar búsqueda"
          title="Limpiar"
          className="absolute right-1 top-1/2 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-md text-meta-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      ) : (
        <kbd
          aria-hidden
          className="pointer-events-none absolute right-2.5 top-1/2 hidden -translate-y-1/2 rounded border border-border bg-muted/60 px-1.5 py-0.5 font-mono text-[10px] leading-none text-meta-foreground sm:block"
        >
          /
        </kbd>
      )}
    </div>
  );
}
