"use client";

// LA MATRIZ DE TRAZABILIDAD — la visual insignia de este artefacto, como la
// matriz de autorización lo es del contrato de API y el diagrama ER del modelo
// de datos.
//
// Una fila por criterio de aceptación, una columna por tipo de caso, y en cada
// cruce cuántos casos lo verifican. Lo que tiene que verse es **el hueco**: una
// fila entera vacía es un criterio que nadie prueba, y esa es la información por
// la que existe la matriz. Un porcentaje de cobertura no sirve para actuar; una
// fila con el nombre del criterio, sí.
//
// El hueco además no vale lo mismo en todas partes: en una historia `must` o
// `should` bloquea el semáforo, en una `could`/`wont` es advertencia (QA-D5). La
// matriz lo distingue en la propia fila, porque leer "12 sin cubrir" sin saber
// cuántos bloquean no dice si el plan se puede ejecutar.
//
// En pantallas estrechas la tabla no se comprime hasta ser ilegible: se cambia
// por una tarjeta por criterio. Una matriz de 40×4 en un móvil no la mira nadie.

import { AlertTriangle, Check, CircleHelp, CircleSlash } from "lucide-react";

import { IdTag, RefChip } from "@/components/artifact/primitives";
import { Badge } from "@/components/ui/badge";
import {
  COVERAGE_STATUS,
  TEST_CASE_KIND,
  TEST_CASE_KIND_ORDER,
} from "@/lib/test-case-kind";
import type { TestCase, TestCaseType, TraceRow } from "@/lib/types/qa";
import { cn } from "@/lib/utils";

/** MoSCoW que hace que un hueco bloquee en vez de avisar. */
const BLOQUEANTES = new Set(["must", "should"]);

export function esBloqueante(row: TraceRow): boolean {
  return BLOQUEANTES.has(row.story_priority ?? "");
}

/** Un hueco que además bloquea el semáforo: lo que hay que resolver primero. */
export function huecosBloqueantes(rows: TraceRow[]): TraceRow[] {
  return rows.filter((r) => r.status !== "covered" && esBloqueante(r));
}

function Cell({
  count,
  type,
}: {
  count: number;
  type: TestCaseType;
}) {
  const style = TEST_CASE_KIND[type];
  if (count === 0) {
    return (
      <span
        className="text-muted-foreground/40"
        title={`Sin casos ${style.label.toLowerCase()}`}
        aria-label="sin casos"
      >
        ·
      </span>
    );
  }
  return (
    <span
      className={cn(
        "inline-flex h-5 min-w-5 items-center justify-center rounded-full px-1.5 text-[11px] font-semibold ring-1 tabular-nums",
        style.badge,
      )}
      title={`${count} ${count === 1 ? "caso" : "casos"} · ${style.hint}`}
    >
      {count}
    </span>
  );
}

export function TraceMatrixView({
  rows,
  cases,
  highlightId,
}: {
  rows: TraceRow[];
  cases: TestCase[];
  /** Id a resaltar al llegar desde un chip de referencia (US-…, AC-…). */
  highlightId?: string;
}) {
  const casosDe = (row: TraceRow) =>
    cases.filter((c) => row.test_case_ids.includes(c.id));

  const cuenta = (row: TraceRow, type: TestCaseType) =>
    casosDe(row).filter((c) => c.type === type).length;

  const resaltada = (row: TraceRow) =>
    highlightId != null &&
    (highlightId === row.criterion_ref || highlightId === row.story_ref);

  if (rows.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        La matriz está vacía: no se mapeó ningún criterio de aceptación.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <Leyenda />

      {/* md+: la matriz. El scroll horizontal vive DENTRO de este contenedor. */}
      <div className="hidden overflow-x-auto md:block">
        <table className="w-full min-w-[42rem] text-xs">
          <thead>
            <tr className="border-b text-left text-muted-foreground">
              <th className="sticky left-0 bg-background py-1.5 pr-3 font-medium">
                Criterio
              </th>
              <th className="px-2 py-1.5 font-medium">Historia</th>
              {TEST_CASE_KIND_ORDER.map((type) => (
                <th
                  key={type}
                  className="px-2 py-1.5 text-center font-medium"
                  title={TEST_CASE_KIND[type].hint}
                >
                  {TEST_CASE_KIND[type].label}
                </th>
              ))}
              <th className="px-2 py-1.5 font-medium">Estado</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const hueco = row.status !== "covered";
              const bloquea = hueco && esBloqueante(row);
              return (
                <tr
                  key={`${row.story_ref}-${row.criterion_ref}`}
                  className={cn(
                    "border-b border-border/50",
                    bloquea && "bg-red-50/60",
                    hueco && !bloquea && "bg-amber-50/40",
                    resaltada(row) && "bg-amber-50 ring-1 ring-amber-300",
                  )}
                >
                  <td className="sticky left-0 bg-inherit py-1.5 pr-3">
                    <span className="flex flex-wrap items-center gap-1.5">
                      <IdTag id={row.criterion_ref} />
                      {row.requirement_refs.map((ref) => (
                        <RefChip key={ref} refId={ref} />
                      ))}
                    </span>
                  </td>
                  <td className="px-2 py-1.5">
                    <span className="flex items-center gap-1.5">
                      <span className="font-mono">{row.story_ref}</span>
                      {row.story_priority && (
                        <span
                          className={cn(
                            "text-[10px] uppercase",
                            esBloqueante(row)
                              ? "font-semibold text-foreground"
                              : "text-muted-foreground",
                          )}
                          title={
                            esBloqueante(row)
                              ? "Historia must/should: un hueco aquí bloquea el semáforo"
                              : "Historia could/wont: un hueco aquí es advertencia"
                          }
                        >
                          {row.story_priority}
                        </span>
                      )}
                    </span>
                  </td>
                  {TEST_CASE_KIND_ORDER.map((type) => (
                    <td key={type} className="px-2 py-1.5 text-center">
                      <Cell count={cuenta(row, type)} type={type} />
                    </td>
                  ))}
                  <td className="px-2 py-1.5">
                    <EstadoBadge row={row} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Por debajo de md: una tarjeta por criterio. */}
      <div className="space-y-2 md:hidden">
        {rows.map((row) => {
          const hueco = row.status !== "covered";
          const bloquea = hueco && esBloqueante(row);
          return (
            <div
              key={`${row.story_ref}-${row.criterion_ref}`}
              className={cn(
                "rounded-lg border p-3 text-xs",
                bloquea && "border-red-300 bg-red-50/60",
              )}
            >
              <div className="flex flex-wrap items-center gap-1.5">
                <IdTag id={row.criterion_ref} />
                <span className="font-mono">{row.story_ref}</span>
                <EstadoBadge row={row} />
              </div>
              <div className="mt-2 flex flex-wrap items-center gap-1.5">
                {row.test_case_ids.length === 0 ? (
                  <span className="text-muted-foreground">Sin casos.</span>
                ) : (
                  casosDe(row).map((c) => (
                    <span
                      key={c.id}
                      className={cn(
                        "rounded px-1.5 py-px font-mono text-[10px] ring-1",
                        TEST_CASE_KIND[c.type].badge,
                      )}
                      title={c.title}
                    >
                      {c.id}
                    </span>
                  ))
                )}
              </div>
            </div>
          );
        })}
      </div>

      <HuecosDetalle rows={rows} />
    </div>
  );
}

function EstadoBadge({ row }: { row: TraceRow }) {
  const style = COVERAGE_STATUS[row.status];
  return (
    <span className="inline-flex items-center gap-1">
      <span
        className={cn(
          "rounded-full px-1.5 py-px text-[10px] ring-1",
          style.badge,
        )}
        title={style.hint}
      >
        {style.label}
      </span>
      {row.question_ref && <RefChip refId={row.question_ref} />}
    </span>
  );
}

function Leyenda() {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
      {TEST_CASE_KIND_ORDER.map((type) => (
        <span key={type} className="inline-flex items-center gap-1">
          <span
            className={cn("h-2 w-2 rounded-full", TEST_CASE_KIND[type].dot)}
          />
          {TEST_CASE_KIND[type].label}
        </span>
      ))}
      <span className="inline-flex items-center gap-1">
        <Check className="h-3 w-3 text-emerald-600" /> cubierto
      </span>
      <span className="inline-flex items-center gap-1">
        <CircleSlash className="h-3 w-3 text-red-500" /> sin cubrir
      </span>
      <span className="inline-flex items-center gap-1">
        <CircleHelp className="h-3 w-3 text-amber-600" /> no verificable
      </span>
    </div>
  );
}

/**
 * Los huecos, enumerados y separados por si bloquean.
 *
 * Es la lectura que la tabla no da de un vistazo cuando hay treinta filas: qué
 * hay que resolver antes de poder ejecutar el plan, y qué queda como aviso.
 */
function HuecosDetalle({ rows }: { rows: TraceRow[] }) {
  const bloquean = huecosBloqueantes(rows);
  const avisan = rows.filter((r) => r.status !== "covered" && !esBloqueante(r));
  if (bloquean.length === 0 && avisan.length === 0) return null;

  return (
    <div className="space-y-2 border-t pt-3 text-xs">
      {bloquean.length > 0 && (
        <div className="rounded-lg border border-red-200 bg-red-50/50 p-2.5">
          <p className="flex items-center gap-1.5 font-medium text-red-700">
            <AlertTriangle className="h-3.5 w-3.5" />
            {bloquean.length} criterio(s) de historias must/should sin cubrir
          </p>
          <p className="mt-0.5 text-muted-foreground">
            El plan no se puede ejecutar completo hasta cubrirlos o declararlos
            no verificables con su pregunta.
          </p>
          <div className="mt-1.5 flex flex-wrap items-center gap-1">
            {bloquean.map((r) => (
              <RefChip key={r.criterion_ref} refId={r.criterion_ref} />
            ))}
          </div>
        </div>
      )}
      {avisan.length > 0 && (
        <div className="rounded-lg border border-amber-200 bg-amber-50/50 p-2.5">
          <p className="font-medium text-amber-700">
            {avisan.length} criterio(s) de historias could/wont sin cubrir
          </p>
          <p className="mt-0.5 text-muted-foreground">
            Advertencia, no bloqueo: su prioridad no exige cobertura.
          </p>
          <div className="mt-1.5 flex flex-wrap items-center gap-1">
            {avisan.map((r) => (
              <RefChip key={r.criterion_ref} refId={r.criterion_ref} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/** Chip del tipo de caso, reutilizado por la lista de casos y el plan. */
export function KindChip({ type }: { type: TestCaseType }) {
  const style = TEST_CASE_KIND[type];
  return (
    <Badge
      variant="outline"
      className={cn("border-transparent ring-1", style.badge)}
      title={style.hint}
    >
      {style.label}
    </Badge>
  );
}
