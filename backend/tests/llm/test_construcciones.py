"""Candado: nadie construye el cliente LLM fuera de la fábrica (LLM0).

Antes de este bloque había 15 sitios que instanciaban el cliente, y cada uno era
un sitio donde una política nueva podía no aplicarse. El peor era
``app/api/v1/inventario.py``: el único camino que se saltaba incluso el runner
del pipeline **y** el que ingiere documentos reales de Urbano.

Este test es de código fuente a propósito. Un test de comportamiento no ve al
que mañana escriba otra construcción directa; un grep sí, y falla en el momento
en que se escribe.
"""

import ast
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]

# Sitios donde el cliente SÍ se construye directamente, y por qué:
#  - el proveedor, que es quien lo construye;
#  - el alias de compatibilidad;
#  - el shim que sostiene la costura del cortafuegos de tests.
PERMITIDOS = {
    "ai/llm/providers/anthropic.py",
    "ai/agents/base/structured.py",
    "app/dependencies/claude.py",
}

# Módulos que ejecutan agentes o ingieren fuentes: todos pasan por la fábrica.
CONSUMIDORES = [
    "app/services/ef_service.py",
    "app/services/scrum_service.py",
    "app/services/arquitectura_service.py",
    "app/services/bd_service.py",
    "app/services/api_service.py",
    "app/services/qa_service.py",
    "ai/orchestrator/nodes.py",
    "ai/orchestrator/scrum_nodes.py",
    "ai/orchestrator/arquitectura_nodes.py",
    "ai/orchestrator/bd_nodes.py",
    "ai/orchestrator/qa_nodes.py",
    "ai/orchestrator/api_nodes.py",
    "app/api/v1/inventario.py",
]


def _fuentes():
    for paquete in ("app", "ai"):
        for ruta in sorted((BACKEND / paquete).rglob("*.py")):
            relativa = ruta.relative_to(BACKEND).as_posix()
            if relativa in PERMITIDOS:
                continue
            yield relativa, ruta.read_text(encoding="utf-8")


def test_ninguna_construccion_directa_del_cliente_fuera_de_la_fabrica():
    infractores = [
        ruta
        for ruta, texto in _fuentes()
        if "ClaudeLLMClient(" in texto or "get_claude_client(" in texto
    ]
    assert (
        infractores == []
    ), "Construyen el cliente sin pasar por ai.llm.get_llm(): " + ", ".join(infractores)


def test_los_consumidores_piden_el_cliente_a_la_fabrica():
    for relativa in CONSUMIDORES:
        texto = (BACKEND / relativa).read_text(encoding="utf-8")
        assert "get_llm(" in texto, f"{relativa} no usa la fábrica"


def test_toda_llamada_a_get_llm_declara_data_class():
    """La firma ya lo obliga; esto lo detecta sin ejecutar la ruta.

    Un ``TypeError`` en el arranque de un job en background es ruidoso, pero se
    ve cuando el job ya falló. Aquí se ve al escribirlo.
    """
    faltantes: list[str] = []
    for relativa in CONSUMIDORES:
        arbol = ast.parse((BACKEND / relativa).read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            if (
                isinstance(nodo, ast.Call)
                and isinstance(nodo.func, ast.Name)
                and nodo.func.id == "get_llm"
            ):
                claves = {kw.arg for kw in nodo.keywords}
                if "data_class" not in claves:
                    faltantes.append(f"{relativa}:{nodo.lineno}")
    assert faltantes == [], "get_llm sin data_class en: " + ", ".join(faltantes)


def test_estan_las_quince_construcciones_redirigidas():
    """Cuenta explícita: 8 en servicios + 6 en nodos + la ingesta del inventario.

    El documento de diseño decía 13; el recuento real del código son 15. Se fija
    el número para que añadir un agente sin pasar por la fábrica no pase
    inadvertido.
    """
    total = 0
    for relativa in CONSUMIDORES:
        arbol = ast.parse((BACKEND / relativa).read_text(encoding="utf-8"))
        total += sum(
            1
            for nodo in ast.walk(arbol)
            if isinstance(nodo, ast.Call)
            and isinstance(nodo.func, ast.Name)
            and nodo.func.id == "get_llm"
        )
    assert total == 15
