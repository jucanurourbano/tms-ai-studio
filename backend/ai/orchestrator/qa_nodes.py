"""Nodos del grafo LangGraph del Agente QA (los doce, completos).

Solo tres tocan el LLM —TEST_DESIGN, EDGE_CASES y el pase de riesgos de CRITIQUE—;
los otros nueve son deterministas, y eso es lo que hace el plan auditable: la
cobertura y el esfuerzo se recomputan leyendo el artefacto y dan el mismo número.
"""

from datetime import date

from langchain_core.runnables import RunnableConfig

from ai.agents.base.structured import ClaudeLLMClient
from ai.agents.qa.assemble import assemble_artifact, validate_artifact
from ai.agents.qa.auth_cases import build_auth_cases
from ai.agents.qa.common import merge_metrics
from ai.agents.qa.consolidate import apply_case_cap
from ai.agents.qa.criterion_map import build_criterion_map
from ai.agents.qa.critique import deterministic_findings, llm_risks
from ai.agents.qa.dataset import build_datasets
from ai.agents.qa.edge_cases import run_edge_cases
from ai.agents.qa.exec_plan import build_execution_plan
from ai.agents.qa.load_sources import (
    assert_scrum_ready,
    extract_sources,
    resolve_api_availability,
    resolve_hashes,
    resolve_target,
)
from ai.agents.qa.question_gen import generate_questions
from ai.agents.qa.state import QaState
from ai.agents.qa.test_design import run_test_design
from ai.agents.qa.trace_matrix import build_trace_matrix, uncovered_requirements_risks
from app.config.settings import settings


def _llm(config: RunnableConfig):
    """LLM inyectado por config (mock en tests); si no, el cliente real."""
    llm = (config or {}).get("configurable", {}).get("llm")
    return llm if llm is not None else ClaudeLLMClient()


def _today(config: RunnableConfig) -> str:
    """Fecha de hoy, inyectable por config para que los bordes sean reproducibles."""
    inyectada = (config or {}).get("configurable", {}).get("today")
    return inyectada or date.today().isoformat()


async def node_load_sources(state: QaState) -> dict:
    """LOAD_SOURCES: gate del plan, contexto consolidado y umbrales efectivos."""
    assert_scrum_ready(bool(state.get("scrum_ready")), state.get("scrum_job_id", "?"))

    scrum_artifact = state.get("scrum_artifact") or {}
    ef_artifact = state.get("ef_artifact") or {}
    api_artifact = state.get("api_artifact") or {}

    disponibilidad = resolve_api_availability(
        state.get("api_job_id"), api_artifact, state.get("api_artifact_hash")
    )
    # Si el contrato no es utilizable, no entra al contexto: así ningún nodo
    # posterior puede derivar un caso de autorización de una fuente a medias.
    usable = api_artifact if disponibilidad["available"] else {}
    sources = extract_sources(scrum_artifact, ef_artifact, usable)

    observaciones: list[dict] = []
    if not disponibilidad["available"]:
        observaciones.append(
            {
                "description": (
                    "No se diseñaron casos de autorización. "
                    f"{disponibilidad['reason']}"
                ),
                "reason": "Dependencia opcional ausente (contrato de API).",
            }
        )

    # Los umbrales efectivos: los de `settings` como base y lo que la petición haya
    # pisado encima. Una sola perilla por concepto — si el target se calculara con
    # sus propios defaults, cambiar `settings` no tendría efecto y el síntoma sería
    # un semáforo que no obedece a su configuración.
    overrides = dict(state.get("target_overrides") or {})
    return {
        "sources": sources,
        "target": resolve_target(
            coverage_threshold=overrides.get(
                "coverage_threshold", settings.QA_COVERAGE_THRESHOLD
            ),
            max_cases_per_criterion=overrides.get(
                "max_cases_per_criterion", settings.QA_MAX_CASES_PER_CRITERION
            ),
            manual_capacity_minutes=overrides.get("manual_capacity_minutes"),
        ),
        "api_available": disponibilidad["available"],
        "api_absent_reason": disponibilidad["reason"],
        "hashes": resolve_hashes(
            state.get("scrum_artifact_hash", ""),
            state.get("ef_artifact_hash", ""),
            state.get("api_artifact_hash"),
            disponibilidad["available"],
        ),
        "map_observations": observaciones,
    }


async def node_criterion_map(state: QaState) -> dict:
    """CRITERION_MAP: andamio determinista de pares (historia, criterio).

    Cortafuegos anti-invención: fija el universo de criterios **antes** de gastar un
    token. Una historia sin criterios se declara aquí y acaba en pregunta.
    """
    mapa = build_criterion_map(state.get("sources") or {})
    observaciones = list(state.get("map_observations") or [])
    for story_ref in mapa.get("stories_without_criteria", []):
        observaciones.append(
            {
                "description": (
                    f"La historia {story_ref} no tiene criterios de aceptación, así "
                    "que no se diseñaron casos para ella."
                ),
                "reason": "Historia sin criterios: no se inventa uno para cubrirla.",
                "source_ref": story_ref,
            }
        )
    return {"criterion_map": mapa, "map_observations": observaciones}


async def node_test_design(state: QaState, config: RunnableConfig) -> dict:
    """TEST_DESIGN: casos funcionales y negativos por criterio (LLM *map*)."""
    salida = await run_test_design(
        _llm(config),
        state.get("criterion_map") or {},
        state.get("sources") or {},
        target=state.get("target"),
        authoritative_context=state.get("authoritative_context"),
    )
    return {
        "test_cases": salida["test_cases"],
        "not_testable": salida["not_testable"],
        "map_observations": list(state.get("map_observations") or [])
        + salida["observations"],
        "metrics": merge_metrics(state, salida["tokens"], salida["skipped"]),
    }


async def node_edge_cases(state: QaState, config: RunnableConfig) -> dict:
    """EDGE_CASES: casos de borde, cada uno con su cita verbatim verificada."""
    casos = list(state.get("test_cases") or [])
    salida = await run_edge_cases(
        _llm(config),
        state.get("criterion_map") or {},
        state.get("sources") or {},
        today=_today(config),
        used_ids={c["id"] for c in casos},
        target=state.get("target"),
        not_testable_refs={
            n_["criterion_ref"]
            for n_ in state.get("not_testable") or []
            if n_.get("criterion_ref")
        },
        authoritative_context=state.get("authoritative_context"),
    )
    return {
        "test_cases": casos + salida["test_cases"],
        "unanchored": salida["unanchored"],
        "map_observations": list(state.get("map_observations") or [])
        + salida["observations"],
        "metrics": merge_metrics(state, salida["tokens"], salida["skipped"]),
    }


async def node_auth_cases(state: QaState) -> dict:
    """AUTH_CASES: casos de autorización derivados de la matriz (sin LLM).

    Último nodo que añade casos, así que aquí se aplica el **techo por criterio**:
    hacerlo después de calcular la matriz y el plan los dejaría contando casos que
    ya no existen, y un total que no cuadra con su lista es peor que un recorte.
    """
    casos = list(state.get("test_cases") or [])
    salida = build_auth_cases(
        state.get("criterion_map") or {},
        state.get("sources") or {},
        used_ids={c["id"] for c in casos},
        target=state.get("target"),
        not_testable_refs={
            n_["criterion_ref"]
            for n_ in state.get("not_testable") or []
            if n_.get("criterion_ref")
        },
    )
    consolidado = apply_case_cap(casos + salida["test_cases"], state.get("target"))
    metrics = dict(state.get("metrics") or {})
    metrics["pruned_cases"] = metrics.get("pruned_cases", 0) + consolidado["pruned"]
    return {
        "test_cases": consolidado["test_cases"],
        "ambiguous_auth_refs": salida["ambiguous_auth_refs"],
        "map_observations": list(state.get("map_observations") or [])
        + salida["observations"]
        + consolidado["observations"],
        "metrics": metrics,
    }


async def node_dataset(state: QaState) -> dict:
    """DATASET: datos reutilizables por entidad, cosechados de los casos (sin LLM)."""
    salida = build_datasets(state.get("test_cases") or [], state.get("sources") or {})
    return {
        "datasets": salida["datasets"],
        "map_observations": list(state.get("map_observations") or [])
        + salida["observations"],
    }


async def node_trace_matrix(state: QaState) -> dict:
    """TRACE_MATRIX: matriz y cobertura, deterministas.

    Se construye **antes** de QUESTION_GEN, así que los criterios no verificables
    todavía no tienen id de pregunta. ASSEMBLE vuelve a cerrar el enlace una vez que
    las preguntas existen: el contrato exige que una fila ``not_testable`` cite la
    suya, y aquí aún no hay ninguna que citar.
    """
    matriz = build_trace_matrix(
        state.get("criterion_map") or {},
        state.get("test_cases") or [],
        state.get("not_testable") or [],
    )
    return {
        "trace_matrix": matriz,
        "risks": list(state.get("risks") or [])
        + uncovered_requirements_risks(matriz["coverage"]),
    }


async def node_exec_plan(state: QaState) -> dict:
    """EXEC_PLAN: suites por épica, orden topológico y esfuerzo (sin LLM)."""
    plan = build_execution_plan(
        state.get("test_cases") or [],
        state.get("sources") or {},
        target=state.get("target"),
    )
    return {"execution_plan": plan}


async def node_critique(state: QaState, config: RunnableConfig) -> dict:
    """CRITIQUE: duplicados, cobertura y ciclos (determinista) + riesgos (LLM)."""
    casos = state.get("test_cases") or []
    matriz = state.get("trace_matrix") or {}
    plan = state.get("execution_plan") or {}

    hallazgos = deterministic_findings(
        casos,
        matriz,
        plan,
        state.get("criterion_map") or {},
        state.get("metrics") or {},
    )
    riesgos_llm, tokens = await llm_risks(
        _llm(config),
        casos,
        matriz,
        plan,
        authoritative_context=state.get("authoritative_context"),
    )
    return {
        "risks": list(state.get("risks") or []) + hallazgos["risks"] + riesgos_llm,
        "observations": list(state.get("observations") or [])
        + hallazgos["observations"],
        "metrics": merge_metrics(state, tokens, []),
    }


async def node_question_gen(state: QaState) -> dict:
    """QUESTION_GEN: preguntas al QA lead, agrupadas por clase de vacío (sin LLM).

    Recalcula la matriz al final para cerrar el enlace ``not_testable`` → pregunta:
    el contrato exige que una fila no verificable cite la pregunta que la respalda, y
    esa pregunta no existía cuando TRACE_MATRIX corrió.
    """
    salida = generate_questions(
        not_testable=state.get("not_testable") or [],
        unanchored=state.get("unanchored") or [],
        ambiguous_auth_refs=state.get("ambiguous_auth_refs") or [],
        criterion_map=state.get("criterion_map") or {},
        trace_matrix=state.get("trace_matrix") or {},
    )
    matriz = build_trace_matrix(
        state.get("criterion_map") or {},
        state.get("test_cases") or [],
        state.get("not_testable") or [],
        salida["questions_by_criterion"],
    )
    return {"questions": salida["questions"], "trace_matrix": matriz}


async def node_assemble(state: QaState) -> dict:
    """ASSEMBLE: arma el QaArtifact y lo revalida contra el esquema v1.0.0."""
    artifact, _has_warnings = assemble_artifact(dict(state))
    datos = artifact.model_dump(mode="json")
    # Revalidación explícita: el ensamblado ya construyó modelos, pero volver a
    # pasar el `dict` por el contrato es lo que garantiza que lo que se PERSISTE
    # —no lo que se tenía en memoria— cumple el esquema.
    validate_artifact(datos)
    return {"artifact": datos, "metrics": datos.get("metrics") or {}}


async def node_persist(state: QaState, config: RunnableConfig) -> dict:
    """PERSIST: guarda el artefacto y marca COMPLETED[_WITH_WARNINGS].

    La persistencia es inyectable por config (tests sin Postgres); si no se
    inyecta, usa la BD real vía ``session_scope``.
    """
    artifact = state["artifact"]
    metrics = artifact.get("metrics") or {}
    # Un plan con casos en cuarentena o con casos podados no pasa por COMPLETED
    # limpio: el equipo tiene que enterarse de que el plan no salió íntegro.
    has_warnings = bool(metrics.get("skipped")) or bool(metrics.get("pruned_cases"))
    status = "COMPLETED_WITH_WARNINGS" if has_warnings else "COMPLETED"

    persist = (config or {}).get("configurable", {}).get("persist")
    if persist is not None:
        await persist(state["job_id"], artifact, status, metrics)
    else:  # pragma: no cover - ruta runtime con Postgres real
        from app.dependencies.database import session_scope
        from app.models.agent import JobStatus
        from app.repositories.agent_job_repository import AgentJobRepository

        async with session_scope() as session:
            repo = AgentJobRepository(session)
            await repo.save_artifact(
                state["job_id"], artifact, artifact["schema_version"]
            )
            await repo.update_job_metrics(state["job_id"], metrics)
            await repo.update_job_status(state["job_id"], JobStatus[status])

    return {"status": status, "metrics": metrics}
