"""Nodo QUESTION_GEN: preguntas al líder técnico (determinístico).

Dos criterios gobiernan este nodo, los mismos que en el Agente BD.

**Qué bloquea.** Lo que haría el contrato inservible o **peligroso**: un endpoint
que nadie puede llamar, un alcance de acceso que no se puede implementar, una regla
de negocio que se evapora, un documento inválido, una autenticación que nadie
decidió. **No** bloquea lo que solo lo hace mejorable: una acción cuyos datos de
entrada están por definir, una celda CRUD sin usar, un actor sin accesos.

Sobre el alcance ambiguo conviene ser explícito, porque **aquí se endurece lo que
decía el diseño**. El diseño lo marcaba como bloqueante solo cuando el endpoint
expone datos personales. Al implementarlo se vio que la distinción no se sostiene:
un alcance que no se puede aplicar significa que quien construya el endpoint lo
construirá **sin restricción alguna**, y eso es un acceso más ancho del que nadie
autorizó — con datos personales o sin ellos. El agravante de la PII no desaparece:
se dice en la propia pregunta, para que se atienda antes.

**Cómo se agrupa.** Cuarenta endpoints sin autorizar son **una** pregunta con los
cuarenta refs enumerados, no cuarenta preguntas. Un panel con cuarenta preguntas
triviales entierra la que de verdad importa, y el afinamiento se abandona.
"""

from typing import Optional

#: Máximo de refs enumerados en el ``reason``. Si hay más, el texto dice cuántos
#: quedan fuera: el recorte se declara, nunca es mudo.
_MAX_REFS_EN_TEXTO = 12


def _enumerar(refs: list[str]) -> str:
    visibles = refs[:_MAX_REFS_EN_TEXTO]
    texto = ", ".join(visibles)
    resto = len(refs) - len(visibles)
    return f"{texto} y {resto} más" if resto > 0 else texto


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


def _nombres(items: list[dict], refs: list[str], clave: str = "operation_id") -> str:
    """Traduce ids a nombres legibles cuando los hay (una pregunta se lee)."""
    por_id = {i["id"]: i.get(clave) or i["id"] for i in items}
    return _enumerar([por_id.get(ref, ref) for ref in refs])


def generate_questions(
    findings: dict,
    endpoints: list[dict],
    schemas: list[dict],
    resource_map: dict,
    target: dict,
) -> list[dict]:
    """Preguntas al líder técnico, agrupadas por clase de vacío."""
    preguntas = _Preguntas()
    recursos = resource_map.get("resources", []) or []

    # --- Bloqueantes ---------------------------------------------------------

    if findings["style_unsupported"]:
        estilo = findings["style_unsupported"][0]
        preguntas.add(
            f"La arquitectura eligió «{estilo}», pero esta especificación es REST. "
            "¿Se rehace con ese estilo o se confirma REST?",
            f"El estilo decidido en la arquitectura es {estilo} y este agente solo "
            "sabe especificar REST. El contrato entregado es aprovechable, pero no "
            "es lo que se pidió.",
            blocking=True,
            ref="target",
        )

    if findings["auth_undecided"]:
        preguntas.add(
            "¿Qué mecanismo de autenticación usa esta API?",
            "La arquitectura no decidió proveedor, así que se aplicó el de la casa. "
            "Toda la matriz de autorización descansa sobre ese mecanismo: no puede "
            "darse por bueno sin confirmarlo.",
            blocking=True,
            ref="target",
        )

    if findings["unauthorized_endpoints"]:
        refs = findings["unauthorized_endpoints"]
        preguntas.add(
            f"¿Quién puede llamar a {'estas operaciones' if len(refs) > 1 else 'esta operación'}? "
            f"({len(refs)} sin autorizar)",
            "Ninguna celda de la matriz CRUD del EF las autoriza, así que quedan "
            "denegadas para todos los actores. Operaciones afectadas: "
            f"{_nombres(endpoints, refs)}.",
            blocking=True,
            ref=refs[0],
        )

    if findings["ambiguous_scopes"]:
        refs = findings["ambiguous_scopes"]
        con_pii = findings["ambiguous_scopes_with_pii"]
        agravante = (
            " Alguna de ellas expone datos personales, así que el error por defecto "
            "sería enseñárselos a quien no debía: "
            f"{_nombres(endpoints, con_pii)}."
            if con_pii
            else ""
        )
        preguntas.add(
            "¿Con qué dato se limita el acceso por filas de estas operaciones? "
            f"({len(refs)} sin resolver)",
            "Una regla del EF restringe qué registros ve cada actor, pero ninguna "
            "columna del modelo de datos permite aplicarla. Tal como está, quien "
            "construya el endpoint lo hará sin restricción alguna. Operaciones "
            f"afectadas: {_nombres(endpoints, refs)}." + agravante,
            blocking=True,
            ref=refs[0],
        )

    if findings["resources_without_operations"]:
        refs = findings["resources_without_operations"]
        preguntas.add(
            f"¿Quién opera sobre {'estos recursos' if len(refs) > 1 else 'este recurso'}? "
            f"({len(refs)} sin ninguna operación)",
            "El EF no tiene celdas en la matriz CRUD para sus entidades, así que no "
            "se generó ningún endpoint: inventarles un dueño habría sido peor. "
            f"Recursos afectados: {_nombres(recursos, refs, 'name')}.",
            blocking=True,
            ref=refs[0],
        )

    if findings["uncovered_ef_apis"]:
        refs = findings["uncovered_ef_apis"]
        preguntas.add(
            f"El EF declara {len(refs)} endpoint(s) que esta especificación no "
            "recoge. ¿Siguen siendo necesarios?",
            f"Endpoints declarados sin equivalente en el contrato: {_enumerar(refs)}.",
            blocking=True,
            ref=refs[0],
        )

    if findings["unenforced_delegated_rules"]:
        refs = findings["unenforced_delegated_rules"]
        preguntas.add(
            f"¿Dónde se hacen cumplir estas {len(refs)} regla(s) de negocio?",
            "El modelo de datos declaró que no puede garantizarlas y las delegó en "
            "la aplicación; la API tampoco las recoge. Tal como está, "
            f"desaparecerían del producto: {_enumerar(refs)}.",
            blocking=True,
            ref=refs[0],
        )

    if findings["spec_errors"]:
        codigos = sorted(set(findings["spec_errors"]))
        preguntas.add(
            "La especificación generada no es válida. ¿Se revisa el contrato de "
            "origen?",
            f"La validación encontró: {_enumerar(codigos)}. Un documento inválido "
            "rompe a los Agentes Backend, Frontend y QA a la vez.",
            blocking=True,
        )

    # --- No bloqueantes ------------------------------------------------------

    if findings["style_undecided"] and not findings["style_unsupported"]:
        preguntas.add(
            "¿Se confirma REST como estilo de esta API?",
            "La arquitectura no lo decidió y se aplicó el default de la casa.",
            blocking=False,
            ref="target",
        )

    if findings["empty_action_inputs"]:
        refs = findings["empty_action_inputs"]
        preguntas.add(
            f"¿Qué datos necesitan {len(refs)} acción(es) de negocio para "
            "ejecutarse?",
            "El EF describe qué hacen pero no qué información hay que enviarles, así "
            "que su cuerpo de entrada quedó declarado y vacío en vez de inventado: "
            f"{_nombres(schemas, refs, 'name')}.",
            blocking=False,
            ref=refs[0],
        )

    if findings["uncovered_crud_cells"]:
        refs = findings["uncovered_crud_cells"]
        preguntas.add(
            f"{len(refs)} celda(s) de la matriz CRUD no se tradujeron en ninguna "
            "operación. ¿Se dan por cubiertas?",
            f"Celdas sin uso: {_enumerar(refs)}. Puede ser correcto (la entidad se "
            "gestiona desde otro recurso) o señal de que falta un endpoint.",
            blocking=False,
            ref=refs[0],
        )

    if findings["actors_without_access"]:
        refs = findings["actors_without_access"]
        preguntas.add(
            f"{len(refs)} actor(es) del EF no tienen acceso a ninguna operación. "
            "¿Es correcto?",
            f"Actores sin accesos: {_enumerar(refs)}. Puede ser que participen en el "
            "proceso sin usar el sistema.",
            blocking=False,
            ref=refs[0],
        )

    if findings["orphan_ef_apis"] or findings["orphan_crud"]:
        refs = findings["orphan_ef_apis"] + findings["orphan_crud"]
        preguntas.add(
            f"{len(refs)} elemento(s) del EF citan entidades que no existen en el "
            "modelo de datos. ¿Se corrige el EF o el modelo?",
            f"Elementos huérfanos: {_enumerar(refs)}.",
            blocking=False,
            ref=refs[0],
        )

    if findings["surface_exceeded"] or findings["resource_surface_exceeded"]:
        detalle = ", ".join(
            findings["surface_exceeded"]
            + [f"recurso {ref}" for ref in findings["resource_surface_exceeded"]]
        )
        preguntas.add(
            "La superficie de la API supera los topes de la casa. ¿Se parte por "
            "módulos?",
            f"Se superó: {detalle}. No se recortó nada: el aviso es para decidir, no "
            "una decisión tomada.",
            blocking=False,
        )

    return preguntas.items


def blocking_refs(questions: list[dict]) -> list[str]:
    """Ids de las preguntas bloqueantes (las que gobiernan el semáforo)."""
    return [q["id"] for q in questions if q["blocking"]]
