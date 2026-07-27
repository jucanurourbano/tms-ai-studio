import { cn } from "@/lib/utils";

/**
 * Envoltorio de tabla con el MISMO lenguaje que las secciones de artefacto
 * (`SectionCard`): card de esquinas suaves, anillo hairline y scroll horizontal
 * propio. Compartido por el historial de jobs y el panel de usuarios para que
 * las superficies secundarias no parezcan de otra aplicación.
 */
export function TableShell({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "overflow-x-auto rounded-xl bg-card ring-1 ring-foreground/10",
        className,
      )}
    >
      {children}
    </div>
  );
}

/**
 * Tipografía de las cabeceras de columna: la misma que `GroupLabel` del
 * artefacto (versalitas de 11px en gris de metadatos). Se pasa por `className`
 * al `TableHead` en vez de tocar la primitiva shadcn de `ui/table`.
 */
export const TH_META =
  "text-[11px] font-semibold uppercase tracking-wide text-meta-foreground";
