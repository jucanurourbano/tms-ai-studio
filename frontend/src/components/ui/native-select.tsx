"use client";

import { cn } from "@/lib/utils";

/**
 * `<select>` nativo con el mismo lenguaje visual que los inputs (altura, borde,
 * foco violeta con glow) y una flecha propia en vez de la del sistema.
 *
 * Se mantiene nativo a propósito: los filtros de tabla son listas cortas, y el
 * select del sistema gana en teclado, accesibilidad y comportamiento en móvil
 * frente a cualquier menú propio.
 */
export function NativeSelect({
  className,
  ...props
}: React.ComponentProps<"select">) {
  return (
    <select
      data-slot="native-select"
      className={cn("field-base field-select", className)}
      {...props}
    />
  );
}
