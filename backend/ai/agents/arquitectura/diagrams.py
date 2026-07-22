"""Nodo DIAGRAMS (determinista): genera Mermaid desde el grafo estructurado.

No interviene el LLM: los diagramas se construyen a partir de los componentes,
contratos e integraciones ya validados, garantizando **sintaxis Mermaid válida**
y reproducible. Dos diagramas: componentes por capa y contexto (sistema ↔
actores/integraciones).
"""

import re


def _mid(ref: str) -> str:
    """Id seguro para Mermaid (alfanumérico + guion bajo)."""
    return re.sub(r"[^0-9A-Za-z]", "_", ref or "")


def _label(text: str) -> str:
    """Etiqueta segura para Mermaid: sin comillas/corchetes ni saltos de línea."""
    clean = " ".join((text or "").split())
    clean = clean.replace('"', "'").replace("[", "(").replace("]", ")")
    return clean[:60] or "—"


def build_component_diagram(
    components: list[dict], contracts: list[dict], integrations: list[dict]
) -> str:
    """Flowchart de componentes agrupados por capa + integraciones + aristas."""
    lines = ["flowchart LR"]

    by_layer: dict[str, list[dict]] = {}
    for c in components:
        by_layer.setdefault(c.get("layer") or "otros", []).append(c)

    for i, (layer, comps) in enumerate(by_layer.items(), start=1):
        lines.append(f'  subgraph L{i}["{_label(layer)}"]')
        for c in comps:
            lines.append(f'    {_mid(c["id"])}["{_label(c["name"])}"]')
        lines.append("  end")

    for ig in integrations:
        lines.append(f'  {_mid(ig["id"])}["{_label(ig["name"])}"]')

    for con in contracts:
        arrow = "-.->" if con.get("kind") in ("external", "event") else "-->"
        lines.append(f'  {_mid(con["from_ref"])} {arrow} {_mid(con["to_ref"])}')

    return "\n".join(lines)


def build_context_diagram(
    actors: list[dict], integrations: list[dict], system_name: str = "Sistema"
) -> str:
    """Diagrama de contexto: actores → sistema → integraciones externas."""
    lines = ["flowchart LR", f'  SYS["{_label(system_name)}"]']
    for i, actor in enumerate(actors, start=1):
        lines.append(f'  ACT{i}["{_label(actor.get("name"))}"] --> SYS')
    for ig in integrations:
        lines.append(f'  SYS -.-> {_mid(ig["id"])}["{_label(ig["name"])}"]')
    return "\n".join(lines)


def build_diagrams(
    components: list[dict],
    contracts: list[dict],
    integrations: list[dict],
    actors: list[dict],
    system_name: str = "Sistema",
) -> dict:
    """Ensambla el bloque ``diagrams`` del artefacto (formato Mermaid)."""
    return {
        "component": {
            "format": "mermaid",
            "code": build_component_diagram(components, contracts, integrations),
        },
        "context": {
            "format": "mermaid",
            "code": build_context_diagram(actors, integrations, system_name),
        },
    }
