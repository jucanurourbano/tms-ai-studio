// Resolución de un id de referencia (REQ-F-001, BR-003, FLD-005…) a la sección
// del hub que lo contiene.
//
// Es lo que permite que un chip de referencia navegue ENTRE paneles: al pulsar
// BR-003 dentro de Preguntas, el panel se cambia a Modelo → Reglas con BR-003
// resaltado. Cada vista de artefacto declara sus rutas por prefijo; la tabla es
// datos puros y por eso se puede testear sin montar nada.

export interface RefTarget {
  /** id de la sección del hub (el mismo del hash: `#modelo`). */
  sectionId: string;
  /** sub-pestaña dentro del panel, si la sección las tiene. */
  tabId?: string;
}

export interface RefRoute extends RefTarget {
  /** Prefijo del id, tal cual lo genera el backend (`REQ-F-`, `BR-`, `SUP-`…). */
  prefix: string;
}

/**
 * Devuelve un resolutor por prefijo. Gana el prefijo **más largo** que encaje,
 * de modo que `REQ-F-` puede apuntar a otra pestaña que `REQ-` sin depender del
 * orden en que se declaren las rutas.
 */
export function makeRefResolver(
  routes: readonly RefRoute[],
): (refId: string) => RefTarget | null {
  const sorted = [...routes].sort((a, b) => b.prefix.length - a.prefix.length);
  return (refId: string) => {
    if (!refId) return null;
    const route = sorted.find((r) => refId.startsWith(r.prefix));
    return route ? { sectionId: route.sectionId, tabId: route.tabId } : null;
  };
}
