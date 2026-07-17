"""Fase INFER: deriva el modelo de datos a partir del modelo consolidado.

Orden: entities -> fields -> relationships -> CRUD -> APIs. Todo lo inferido
lleva ``origin='derived'``. Inferencia determinística (sin LLM), fácil de testear.
"""

import re
import unicodedata
from typing import Any


def _norm(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text or "")
    sin_acentos = "".join(c for c in nfkd if not unicodedata.combining(c))
    return " ".join(sin_acentos.lower().split())


def _slug_plural(name: str) -> str:
    """Genera un segmento de ruta en plural simple a partir del nombre."""
    base = _norm(name).replace(" ", "_")
    if not base:
        return "recursos"
    return base if base.endswith("s") else base + "s"


def infer(consolidated: dict[str, Any]) -> dict[str, Any]:
    """Deriva entities, relationships, CRUD y APIs del modelo consolidado."""
    fields: list[dict] = [dict(f) for f in consolidated.get("fields", [])]
    actors: list[dict] = consolidated.get("actors", [])

    # 1) Entities: a partir de los entity_ref distintos de los campos.
    name_to_id: dict[str, str] = {}
    entities: list[dict] = []
    for field in fields:
        ref = field.get("entity_ref")
        if ref and _norm(ref) not in name_to_id:
            eid = f"ENT-{len(entities) + 1:03d}"
            name_to_id[_norm(ref)] = eid
            entities.append(
                {
                    "id": eid,
                    "name": ref,
                    "origin": "derived",
                    "confidence": 0.6,
                    "source_ref": field.get("source_ref"),
                }
            )

    # 2) Fields: remapear entity_ref (nombre) -> id de entidad.
    for field in fields:
        ref = field.get("entity_ref")
        if ref:
            field["entity_ref"] = name_to_id.get(_norm(ref), ref)

    # 3) Relationships: campos '<x>_id' que referencian a otra entidad.
    relationships: list[dict] = []
    for field in fields:
        fname = field.get("name", "")
        if re.search(r"_id$", fname):
            referenced = fname[:-3]
            target_id = name_to_id.get(_norm(referenced))
            owner_id = field.get("entity_ref")
            if target_id and owner_id and target_id != owner_id:
                relationships.append(
                    {
                        "id": f"REL-{len(relationships) + 1:03d}",
                        "source_entity_ref": target_id,
                        "target_entity_ref": owner_id,
                        "cardinality": "1:N",
                        "origin": "derived",
                        "confidence": 0.5,
                    }
                )

    # 4) CRUD: por entidad (read/create/update derivados; delete conservador).
    first_actor = actors[0]["id"] if actors else None
    crud: list[dict] = []
    for i, ent in enumerate(entities, start=1):
        crud.append(
            {
                "id": f"CRUD-{i:03d}",
                "entity_ref": ent["id"],
                "actor_ref": first_actor,
                "create": True,
                "read": True,
                "update": True,
                "delete": False,
                "origin": "derived",
                "confidence": 0.5,
            }
        )

    # 5) APIs: GET (listar) y POST (crear) por entidad.
    apis: list[dict] = []
    for ent in entities:
        plural = _slug_plural(ent["name"])
        for method in ("GET", "POST"):
            apis.append(
                {
                    "id": f"API-{len(apis) + 1:03d}",
                    "method": method,
                    "path": f"/api/v1/{plural}",
                    "entity_ref": ent["id"],
                    "origin": "derived",
                    "confidence": 0.5,
                }
            )

    return {
        "entities": entities,
        "fields": fields,
        "relationships": relationships,
        "crud": crud,
        "apis": apis,
    }
