"use client";

// Contexto de navegación por referencias dentro del centro de comando.
//
// Los chips de referencia (`RefChip`) no saben nada del hub: piden "llévame a
// REQ-F-001" y quien resuelva decide si eso significa cambiar de panel, resaltar
// una fila o avisar de que ese id no vive en este artefacto. Cuando no hay
// proveedor (impresión, vistas antiguas) el chip cae al comportamiento anterior
// de desplazarse por el documento.

import { createContext, useContext, useMemo } from "react";

export interface ArtifactNavApi {
  /** Abre el panel de la sección que contiene `refId` y lo resalta. */
  navigateToRef: (refId: string) => void;
  /** true si el id es alcanzable (para pintar el chip como navegable). */
  canNavigateToRef: (refId: string) => boolean;
}

const ArtifactNavContext = createContext<ArtifactNavApi | null>(null);

export function ArtifactNavProvider({
  navigateToRef,
  canNavigateToRef,
  children,
}: ArtifactNavApi & { children: React.ReactNode }) {
  const value = useMemo(
    () => ({ navigateToRef, canNavigateToRef }),
    [navigateToRef, canNavigateToRef],
  );
  return (
    <ArtifactNavContext.Provider value={value}>
      {children}
    </ArtifactNavContext.Provider>
  );
}

/** `null` fuera del hub: el consumidor decide su plan B. */
export function useArtifactNav(): ArtifactNavApi | null {
  return useContext(ArtifactNavContext);
}
