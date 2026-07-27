import { cn } from "@/lib/utils";

/**
 * Contenedor de página: una sola decisión de ancho para toda la app.
 *
 * Estrategia (sustituye a los `max-w-5xl` sueltos que dejaban medio monitor
 * vacío):
 *
 * - `work` (por defecto) — **fluido**. Las vistas de trabajo (tablas, backlog,
 *   historiales, panel de usuarios, grids del dashboard) ocupan el ancho
 *   disponible, que es justo lo que se gana al colapsar la sidebar o el índice
 *   del artefacto. Padding lateral cómodo (24px, 32px en `lg`).
 * - `form` — acotado (`max-w-3xl`) para formularios de una columna, donde estirar
 *   los campos a 1600px sería peor, no mejor.
 * - `notice` — estrecho (`max-w-2xl`) para avisos y estados de carga/error.
 *
 * En pantallas ultra anchas todo se corona en **1600px centrado**: más allá, las
 * filas de tabla se vuelven ilegibles de tan largas y el ojo pierde la relación
 * entre la primera y la última columna.
 *
 * La **prosa se acota localmente**, no aquí: los párrafos largos usan
 * `max-w-prose` dentro de este contenedor ancho. El contenedor es ancho; el
 * texto, no.
 */
export function PageContainer({
  variant = "work",
  className,
  children,
}: {
  variant?: "work" | "form" | "notice";
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "mx-auto w-full px-6 py-6 lg:px-8",
        variant === "work" && "max-w-[1600px]",
        variant === "form" && "max-w-3xl",
        variant === "notice" && "max-w-2xl",
        className,
      )}
    >
      {children}
    </div>
  );
}
