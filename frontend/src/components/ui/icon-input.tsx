"use client";

import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * Input con **icono interno a la izquierda**, para los campos donde el icono
 * aporta reconocimiento inmediato (correo, usuario). No se pone icono "porque
 * queda bonito": en un campo de texto genérico solo roba espacio.
 */
export function IconInput({
  icon: Icon,
  className,
  invalid,
  ...props
}: React.ComponentProps<"input"> & { icon: LucideIcon; invalid?: boolean }) {
  return (
    <div className="relative">
      <Icon className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-meta-foreground" />
      <input
        aria-invalid={invalid || undefined}
        className={cn("field-base pl-9", className)}
        {...props}
      />
    </div>
  );
}
