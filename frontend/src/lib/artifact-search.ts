// Buscador LOCAL de un panel de artefacto.
//
// El panel universal filtra la sección que tiene abierta, no todo el artefacto:
// escribir "checkpoint" en Requisitos deja los requisitos que lo mencionan, y lo
// mismo en Historias o en Reglas. La comparación ignora acentos y mayúsculas
// porque el contenido está en español y nadie escribe "ambigüedad" con diéresis
// al buscar.

/** Minúsculas sin acentos (NFD + descarte de diacríticos). */
export function normalizeText(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

/**
 * Trocea la consulta en términos y exige que **todos** aparezcan en alguno de
 * los campos (AND por término, OR por campo). Consulta vacía ⇒ siempre encaja,
 * para que el render no tenga que distinguir "sin filtro".
 */
export function matchesQuery(
  query: string,
  ...fields: (string | number | null | undefined)[]
): boolean {
  const terms = normalizeText(query).split(/\s+/).filter(Boolean);
  if (terms.length === 0) return true;
  const haystack = normalizeText(
    fields.filter((f) => f !== null && f !== undefined).join("  "),
  );
  return terms.every((t) => haystack.includes(t));
}

/** Filtra una lista con `matchesQuery` sobre los campos que devuelve `textOf`. */
export function filterByQuery<T>(
  query: string,
  items: readonly T[],
  textOf: (item: T) => (string | number | null | undefined)[],
): T[] {
  if (!query.trim()) return items as T[];
  return items.filter((item) => matchesQuery(query, ...textOf(item)));
}
