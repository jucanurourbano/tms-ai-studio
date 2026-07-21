import { Skeleton } from "@/components/ui/skeleton";

/** Placeholder de carga para las vistas de artefacto (EF y Scrum). */
export function ArtifactSkeleton() {
  return (
    <div className="flex flex-col" aria-busy="true" aria-label="Cargando artefacto">
      {/* Barra superior */}
      <div className="flex flex-wrap items-center gap-3 border-b px-6 py-3">
        <Skeleton className="h-6 w-28" />
        <Skeleton className="h-6 w-20" />
        <Skeleton className="h-6 w-40" />
        <Skeleton className="ml-auto h-7 w-28" />
      </div>
      {/* Cabecera de métricas */}
      <div className="space-y-2 border-b px-6 py-4">
        <Skeleton className="h-4 w-2/3" />
        <Skeleton className="h-4 w-1/2" />
      </div>
      {/* Índice + contenido */}
      <div className="grid grid-cols-1 gap-6 px-4 py-5 md:grid-cols-[13rem_1fr] md:px-6">
        <div className="hidden space-y-2 md:block">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-7 w-full" />
          ))}
        </div>
        <div className="space-y-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="space-y-2 rounded-md border p-4">
              <Skeleton className="h-4 w-40" />
              <Skeleton className="h-3 w-full" />
              <Skeleton className="h-3 w-5/6" />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
