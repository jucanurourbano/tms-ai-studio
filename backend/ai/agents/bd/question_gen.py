"""Nodo QUESTION_GEN: preguntas al DBA/Arquitecto (determinístico).

Dos criterios gobiernan este nodo.

**Qué bloquea.** Bloquea lo que haría inservible o peligroso el modelo: una entidad
del EF sin tabla, un motor que nadie decidió, un DDL inválido, una relación que no
se pudo materializar. **No** bloquea lo que solo lo hace mejorable: una longitud por
defecto, una política de retención, un catálogo pendiente de valores. Si todo
bloqueara, el semáforo no distinguiría nada.

**Cómo se agrupa.** Cuarenta columnas sin longitud son **una** pregunta con los
cuarenta refs enumerados, no cuarenta preguntas. Un panel con cuarenta preguntas
triviales entierra la que de verdad importa, y el afinamiento se abandona. Cuando
se agrupa, el texto dice cuántos casos cubre y ``reason`` los enumera (con tope
declarado, nunca un recorte mudo).
"""

from typing import Any, Optional

#: Máximo de refs enumerados en el `reason` de una pregunta agrupada. Si hay más,
#: el propio texto dice cuántos quedan fuera.
_MAX_REFS_EN_TEXTO = 12


class _Preguntas:
    """Acumulador con numeración estable."""

    def __init__(self) -> None:
        self.items: list[dict] = []

    def add(
        self,
        question: str,
        reason: str,
        *,
        blocking: bool,
        ref: Optional[str] = None,
        confidence: Optional[float] = None,
    ) -> None:
        self.items.append(
            {
                "id": f"Q-{len(self.items) + 1:03d}",
                "question": question,
                "reason": reason,
                "audience": "tecnico",
                "blocking": blocking,
                "linked_to_ref": ref,
                "status": "pendiente",
                "confidence": confidence,
                "origin": "derived",
            }
        )


def _enumerar(refs: list[str]) -> str:
    """Enumera refs para el ``reason``, declarando lo que no cabe."""
    visibles = refs[:_MAX_REFS_EN_TEXTO]
    texto = ", ".join(visibles)
    resto = len(refs) - len(visibles)
    return f"{texto} y {resto} más" if resto > 0 else texto


def generate_questions(critique: dict[str, Any]) -> list[dict]:
    """Genera las preguntas al DBA desde los hallazgos de CRITIQUE."""
    findings = critique.get("findings", {}) or {}
    coverage = findings.get("coverage", {}) or {}
    preguntas = _Preguntas()

    # --- Bloqueantes --------------------------------------------------------

    # 1) Motor sin decidir: todo el DDL depende de esto.
    if findings.get("engine_undecided"):
        preguntas.add(
            (
                "¿Sobre qué motor relacional se construye este sistema? El diseño "
                "de arquitectura no lo decidió y se ha modelado con el motor por "
                "defecto de la casa."
            ),
            reason=(
                "El motor determina tipos, sintaxis del DDL y límites de "
                "identificador: confirmarlo es previo a ejecutar nada."
            ),
            blocking=True,
        )

    # 2) Entidades del EF sin tabla: el modelo estaría incompleto.
    sin_tabla = coverage.get("uncovered_entity_refs") or []
    if sin_tabla:
        preguntas.add(
            (
                f"{len(sin_tabla)} entidad(es) del EF no tienen tabla en el modelo. "
                "¿Deben modelarse o quedan fuera del alcance de datos?"
            ),
            reason=f"Entidades sin tabla: {_enumerar(sin_tabla)}.",
            blocking=True,
            ref=sin_tabla[0],
        )

    # 3) DDL inválido: entregar un esquema que no se puede ejecutar.
    errores = findings.get("ddl_errors") or []
    if errores:
        codigos = sorted({e.get("code", "?") for e in errores})
        preguntas.add(
            (
                f"El DDL generado tiene {len(errores)} error(es) estructurales "
                f"({', '.join(codigos)}). ¿Cómo debe corregirse el modelo?"
            ),
            reason=(
                "Un esquema que no se puede ejecutar no sirve al Agente API ni al "
                "equipo: hay que resolverlo antes de continuar."
            ),
            blocking=True,
            ref=errores[0].get("ref"),
        )

    # 4) Relaciones 1:1 sin dueño: la relación no llegó al esquema.
    for pendiente in findings.get("unresolved_one_to_one") or []:
        candidatos = " o ".join(pendiente.get("candidates", []))
        preguntas.add(
            (
                f"En la relación 1:1 {pendiente['relationship_ref']}, ¿qué tabla "
                f"debe llevar la clave foránea: {candidatos}?"
            ),
            reason=(
                "No se pudo determinar qué lado depende del otro, así que la "
                "relación no se materializó en el esquema."
            ),
            blocking=True,
            ref=pendiente["relationship_ref"],
        )

    # 5) Relaciones que citan entidades inexistentes: inconsistencia del EF.
    huerfanas = findings.get("orphan_relationships") or []
    if huerfanas:
        refs = [r["relationship_ref"] for r in huerfanas]
        preguntas.add(
            (
                f"{len(huerfanas)} relación(es) del EF citan entidades que no "
                "existen. ¿Se corrigen en el EF o se descartan?"
            ),
            reason=f"Relaciones afectadas: {_enumerar(refs)}.",
            blocking=True,
            ref=refs[0],
        )

    # 6) Tipos ambiguos en columnas OBLIGATORIAS: el tipo condiciona los datos.
    ambiguos = findings.get("ambiguous_type_columns") or []
    obligatorios = [c for c in ambiguos if c.get("required")]
    if obligatorios:
        refs = [f"{c['table']}.{c['column']}" for c in obligatorios]
        preguntas.add(
            (
                f"{len(obligatorios)} columna(s) obligatoria(s) tienen un tipo que "
                "no se pudo deducir del EF. ¿Qué tipo y tamaño deben llevar?"
            ),
            reason=(
                f"Columnas afectadas: {_enumerar(refs)}. Se aplicó un tipo "
                "conservador para no bloquear el diseño."
            ),
            blocking=True,
            ref=obligatorios[0].get("ref"),
        )

    # --- No bloqueantes -----------------------------------------------------

    # 7) Tipos ambiguos en columnas opcionales.
    opcionales = [c for c in ambiguos if not c.get("required")]
    if opcionales:
        refs = [f"{c['table']}.{c['column']}" for c in opcionales]
        preguntas.add(
            (
                f"{len(opcionales)} columna(s) opcional(es) llevan un tipo por "
                "defecto. ¿Se confirman?"
            ),
            reason=f"Columnas afectadas: {_enumerar(refs)}.",
            blocking=False,
            ref=opcionales[0].get("ref"),
        )

    # 8) Campos del EF que no llegaron a ninguna columna.
    sin_columna = coverage.get("unmapped_field_refs") or []
    if sin_columna:
        preguntas.add(
            (
                f"{len(sin_columna)} campo(s) del EF no están en ninguna tabla. "
                "¿A qué entidad pertenecen?"
            ),
            reason=(
                f"Campos sin entidad declarada: {_enumerar(sin_columna)}. Sin "
                "`entity_ref` no se puede saber en qué tabla van."
            ),
            blocking=False,
            ref=sin_columna[0],
        )

    # 9) Reglas y validaciones que el esquema no hace cumplir.
    no_aplicadas = sorted(
        {
            *(coverage.get("unenforced_validation_refs") or []),
            *(coverage.get("unenforced_rule_refs") or []),
        }
    )
    if no_aplicadas:
        preguntas.add(
            (
                f"{len(no_aplicadas)} regla(s) del EF no se hacen cumplir en el "
                "esquema y quedan para la capa de aplicación. ¿Se confirma?"
            ),
            reason=(
                f"Reglas afectadas: {_enumerar(no_aplicadas)}. No son expresables "
                "como constraint declarativa (comparan con la fecha actual, "
                "cruzan varias filas o exigen lógica de negocio)."
            ),
            blocking=False,
            ref=no_aplicadas[0],
        )

    # 10) Catálogos creados sin valores.
    catalogos = findings.get("catalogs_without_seed") or []
    if catalogos:
        preguntas.add(
            (
                f"{len(catalogos)} catálogo(s) se crearon sin valores iniciales. "
                "¿Cuáles son los valores válidos?"
            ),
            reason=(
                f"Catálogos afectados: {_enumerar(catalogos)}. El EF menciona la "
                "clasificación pero no enumera sus valores, y no se inventan."
            ),
            blocking=False,
            ref=None,
        )

    # 11) Datos personales sin política declarada.
    pii = findings.get("pii_columns") or []
    if pii:
        refs = [f"{c['table']}.{c['column']}" for c in pii]
        preguntas.add(
            (
                f"{len(pii)} columna(s) parecen contener datos personales. ¿Requieren "
                "cifrado, enmascarado o una política de retención concreta?"
            ),
            reason=(
                f"Columnas afectadas: {_enumerar(refs)}. El modelo no aplica ningún "
                "tratamiento especial: la decisión es del DBA y del responsable de "
                "datos."
            ),
            blocking=False,
            ref=pii[0].get("ref"),
        )

    # 12) Tablas sin relación con el resto.
    aisladas = findings.get("orphan_tables") or []
    if aisladas:
        preguntas.add(
            (
                f"{len(aisladas)} tabla(s) no participan en ninguna relación. "
                "¿Falta alguna relación en el EF?"
            ),
            reason=f"Tablas aisladas: {_enumerar(aisladas)}.",
            blocking=False,
            ref=None,
        )

    # 13) Tablas derivadas con poca confianza.
    dudosas = findings.get("low_confidence_tables") or []
    if dudosas:
        refs = [t["table"] for t in dudosas]
        preguntas.add(
            (
                f"{len(dudosas)} tabla(s) se derivaron con baja confianza. ¿Se "
                "confirman como parte del modelo?"
            ),
            reason=f"Tablas afectadas: {_enumerar(refs)}.",
            blocking=False,
            ref=dudosas[0].get("ref"),
        )

    return preguntas.items
