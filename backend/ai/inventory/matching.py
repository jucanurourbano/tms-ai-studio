"""Emparejamiento léxico y estructural contra el inventario (INV4, v1).

Responde una sola pregunta: *lo que el agente propone crear, ¿ya existe?*

**Sin embeddings.** v1 compara nombres normalizados (sin acentos, sin plural, sin
prefijos de la casa) y, cuando hay columnas, el solapamiento estructural. Es
suficiente para lo que domina en la práctica —"Trabajador" contra la tabla
``usuarios``, "envío" contra ``envios``— y tiene la virtud de ser explicable: se
puede enseñar POR QUÉ se emparejaron dos cosas.

Gancho para v2 (pgvector)
-------------------------
Lo que falla aquí son los sinónimos sin parecido léxico: "Colaborador" y
``usuarios`` no comparten un solo carácter relevante. La solución es semántica y
está prevista: la extensión ``pgvector`` YA está disponible en la imagen de
Postgres (v1 no la usa, ver CLAUDE.md §10). El punto de extensión es
:func:`name_similarity`: basta sumar la similitud coseno de los embeddings de
ambos nombres y quedarse con el máximo de las dos señales. Nada más de este
módulo cambia — ni los umbrales, ni :func:`classify`, ni los llamantes.

Mientras tanto, el caso que la comparación léxica NO resuelve no se resuelve mal:
cae en la banda de duda y se convierte en **pregunta al humano**. Es la diferencia
entre no saber y equivocarse.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Optional

# --- Umbrales (calibrados con tests, como el Jaccard del Scrum) --------------

#: Por encima de esto, dos nombres son LA MISMA cosa sin preguntar.
NAME_MATCH_THRESHOLD = 0.82

#: Por debajo de esto no hay parecido: es un elemento nuevo.
NAME_DOUBT_THRESHOLD = 0.55

#: Solapamiento de columnas por encima del cual dos tablas parecidas de nombre se
#: consideran la misma estructura (y no un choque).
STRUCTURE_MATCH_THRESHOLD = 0.60

#: Prefijos y sufijos que la casa añade sin cambiar el significado. "tbl_usuarios"
#: y "usuarios" son la misma tabla; compararlas en crudo daría 0.62 y caería en la
#: banda de duda, generando una pregunta inútil.
_AFIJOS = ("tbl_", "tb_", "t_", "mst_", "cat_", "dim_", "_tbl", "_master", "_maestro")

#: Sinónimos del dominio que NO se parecen léxicamente pero son la misma entidad.
#: Es una lista corta y explícita a propósito: cada entrada es una decisión que
#: alguien tomó, no una inferencia. Lo que no esté aquí y no se parezca cae en la
#: banda de duda y se pregunta — que es el comportamiento correcto.
_SINONIMOS: dict[str, str] = {
    "trabajador": "usuario",
    "trabajadores": "usuario",
    "colaborador": "usuario",
    "colaboradores": "usuario",
    "empleado": "usuario",
    "empleados": "usuario",
    "personal": "usuario",
    "shipper": "cliente",
    "shippers": "cliente",
    "remitente": "cliente",
    "remitentes": "cliente",
    "guia": "envio",
    "guias": "envio",
    "courier": "courier",
    "mensajero": "courier",
    "repartidor": "courier",
}


def strip_accents(text: str) -> str:
    """Quita acentos y diacríticos (``envío`` → ``envio``)."""
    nfkd = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def singularize(word: str) -> str:
    """Singular aproximado en español, suficiente para nombres de tabla/entidad.

    No es un lematizador: cubre las terminaciones que aparecen en nombres de
    tablas (``usuarios``→``usuario``, ``direcciones``→``direccion``). Un caso raro
    que quede mal singularizado baja el parecido y acaba en pregunta, no en un
    emparejamiento equivocado.
    """
    palabra = word.lower()
    if len(palabra) <= 3:
        return palabra
    if palabra.endswith("ces"):  # matrices -> matriz
        return palabra[:-3] + "z"
    if palabra.endswith("es") and len(palabra) > 4:
        # En español el plural en «-es» solo se forma sobre singulares acabados
        # en CONSONANTE FINAL VÁLIDA (camiones→camion, direcciones→direccion).
        # Si quitar «es» deja algo que no puede terminar una palabra española, el
        # singular sale de quitar solo la «s»: clientes→cliente, NO «client».
        # Quitar siempre «es» era el bug que hacía que «Cliente» y «clientes» no
        # se emparejaran.
        # La «d» queda FUERA del conjunto a propósito: «-des» es ambiguo
        # (`sedes`→`sede` pero `redes`→`red`) y en este dominio la primera forma
        # es la frecuente (sedes, redes de atención no son tablas). El caso raro
        # cae en la banda de duda y se pregunta, que es el fallo barato.
        raiz = palabra[:-2]
        if raiz and raiz[-1] in "nrlzjxy":
            return raiz
        return palabra[:-1]
    if palabra.endswith("s") and not palabra.endswith("ss"):
        return palabra[:-1]
    return palabra


def normalize_name(name: str) -> str:
    """Nombre canónico: sin acentos, sin afijos de la casa, en singular.

    ``Trabajadores`` → ``trabajador``; ``tbl_Usuarios`` → ``usuario``;
    ``motivos_devolucion`` → ``motivo devolucion``.
    """
    texto = strip_accents(name or "").lower().strip()
    for afijo in _AFIJOS:
        if afijo.startswith("_") and texto.endswith(afijo):
            texto = texto[: -len(afijo)]
        elif texto.startswith(afijo):
            texto = texto[len(afijo) :]
    tokens = [t for t in re.split(r"[^a-z0-9]+", texto) if t]
    return " ".join(singularize(t) for t in tokens)


def canonical_name(name: str) -> str:
    """Nombre normalizado con los sinónimos del dominio ya aplicados."""
    normalizado = normalize_name(name)
    tokens = normalizado.split()
    if not tokens:
        return normalizado
    # El sinónimo se aplica sobre el nombre completo y sobre el primer token, que
    # es el que lleva el significado en `trabajador_area` o `guia_electronica`.
    if normalizado in _SINONIMOS:
        return _SINONIMOS[normalizado]
    tokens[0] = _SINONIMOS.get(tokens[0], tokens[0])
    return " ".join(tokens)


def jaccard(a: set[str], b: set[str]) -> float:
    """Índice de Jaccard (mismo criterio que el deduplicador del Scrum)."""
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def _trigrams(text: str) -> set[str]:
    """Trigramas de caracteres, para medir parecido dentro de una palabra."""
    limpio = f"  {text.replace(' ', '')}  "
    return {limpio[i : i + 3] for i in range(len(limpio) - 2)}


def name_similarity(a: str, b: str) -> float:
    """Parecido entre dos nombres, en ``[0, 1]``.

    Combina dos señales porque cada una falla donde la otra acierta: el Jaccard de
    tokens no ve el parecido DENTRO de una palabra (``usuario`` vs ``usuarios`` ya
    normalizados coinciden, pero ``direccion`` vs ``direcciones`` mal
    singularizados no), y el de trigramas sobrevalora palabras cortas que comparten
    letras. Se toma el máximo: basta con que una de las dos vea el parecido.

    **Punto de extensión para pgvector (v2)**: añadir aquí la similitud coseno de
    los embeddings y devolver el máximo de las tres señales. Ni los umbrales ni
    :func:`classify` necesitan cambiar.
    """
    ca, cb = canonical_name(a), canonical_name(b)
    if not ca or not cb:
        return 0.0
    if ca == cb:
        return 1.0
    por_tokens = jaccard(set(ca.split()), set(cb.split()))
    por_trigramas = jaccard(_trigrams(ca), _trigrams(cb))
    return max(por_tokens, por_trigramas)


def column_overlap(propuestas: list[str], existentes: list[str]) -> float:
    """Fracción de columnas propuestas que ya existen (nombres normalizados).

    Se mide sobre las PROPUESTAS y no sobre la unión a propósito: lo que importa
    para decidir *reuse* frente a *extend* es cuánto de lo que se pide ya está,
    no cuánto de la tabla existente se usa. Una tabla de producción con 40
    columnas de las que el diseño nuevo necesita 5 sigue siendo reutilizable.
    """
    if not propuestas:
        return 0.0
    canon_existentes = {canonical_name(c) for c in existentes}
    presentes = sum(1 for c in propuestas if canonical_name(c) in canon_existentes)
    return presentes / len(propuestas)


# --- Resultado ---------------------------------------------------------------


@dataclass
class MatchCandidate:
    """Un elemento del inventario que podría ser el mismo que el propuesto."""

    name: str
    asset_id: str
    asset_name: str
    system_id: str
    system_name: str
    name_score: float
    structure_score: Optional[float] = None
    #: Contenido del elemento existente (tabla, endpoint…), para poder mostrarlo
    #: al lado de la propuesta en la UI.
    payload: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "asset_id": self.asset_id,
            "asset_name": self.asset_name,
            "system_id": self.system_id,
            "system_name": self.system_name,
            "name_score": round(self.name_score, 3),
            "structure_score": (
                round(self.structure_score, 3)
                if self.structure_score is not None
                else None
            ),
        }


def best_candidate(
    nombre: str,
    candidatos: list[MatchCandidate],
) -> Optional[MatchCandidate]:
    """Candidato de mayor parecido de nombre (desempate estable por nombre)."""
    if not candidatos:
        return None
    return sorted(
        candidatos,
        key=lambda c: (-c.name_score, c.name),
    )[0]
