// Borrador de la respuesta que se está escribiendo, **aislado por pregunta**.
//
// Esto existe por un bug de corrupción de datos real: en el modo "una a una" los
// controles de validación ocupan siempre la misma posición del árbol, así que React
// **reutiliza la instancia** al cambiar de pregunta y el `useState` inicial no se
// vuelve a ejecutar. El texto escrito para una pregunta seguía en la caja al
// avanzar a la siguiente y, si se pulsaba Confirmar, se guardaba esa misma
// respuesta en otra pregunta. Pasó de verdad: en el EF de vacaciones, Q-005 quedó
// con la respuesta literal de Q-004.
//
// La regla vive aquí, fuera del componente, porque es lo que hay que blindar con
// un test: qué texto debe haber en la caja en cada momento.

/** Estado del borrador: a qué pregunta pertenece y qué respuesta guardada refleja. */
export interface ValidationDraft {
  /** Pregunta a la que pertenece el texto. */
  targetId: string;
  /** Respuesta guardada que se cargó (para detectar cambios venidos del servidor). */
  source: string;
  /** Lo que hay ahora en la caja. */
  text: string;
}

/** Borrador inicial de una pregunta: su respuesta guardada, o vacío si no tiene. */
export function draftFor(
  targetId: string,
  respuesta?: string | null,
): ValidationDraft {
  const source = respuesta ?? "";
  return { targetId, source, text: source };
}

/**
 * Borrador que corresponde a este render, o `null` si el actual sigue siendo válido.
 *
 * Se reinicia en dos casos y **solo** en esos dos:
 *
 * 1. **Cambió la pregunta**: el texto de la anterior no puede sobrevivir al salto.
 *    Es el bug que originó este módulo.
 * 2. **Cambió la respuesta guardada** que se está reflejando: alguien la actualizó
 *    fuera de la caja (se guardó, o se restableció a pendiente y quedó vacía).
 *
 * Lo que NO reinicia es el tecleo: mientras la pregunta y su respuesta guardada
 * sigan siendo las mismas, lo escrito se respeta aunque el padre se re-renderice
 * (y se re-renderiza en cada recarga del resumen de validaciones).
 */
export function syncDraft(
  current: ValidationDraft,
  targetId: string,
  respuesta?: string | null,
): ValidationDraft | null {
  const source = respuesta ?? "";
  if (current.targetId === targetId && current.source === source) return null;
  return { targetId, source, text: source };
}
