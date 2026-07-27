"use client";

import { cn } from "@/lib/utils";

/**
 * Papel de la columna en la **card** de móvil. En escritorio todas son columnas;
 * al bajar de `md` cada fila se convierte en card y el papel decide dónde va:
 *
 * - `title`   → título prominente arriba (una por tabla).
 * - `meta`    → línea secundaria bajo el título (correo, id…).
 * - `badge`   → chips agrupados en una fila propia.
 * - `actions` → arriba a la derecha (menú ⋮).
 * - `pair`    → par etiqueta-valor en la rejilla de 2 columnas (por defecto).
 * - `hidden`  → se omite en móvil (dato redundante en ese contexto).
 */
export type CardRole =
  | "title"
  | "meta"
  | "badge"
  | "actions"
  | "pair"
  | "hidden";

export interface DataColumn<T> {
  key: string;
  /** Etiqueta de cabecera; también la etiqueta del par en móvil. */
  label: string;
  render: (row: T) => React.ReactNode;
  /** Números: alineados a la derecha con tipografía tabular. */
  numeric?: boolean;
  /** Ancho fijo de la columna en escritorio (clase Tailwind, p. ej. `w-24`). */
  width?: string;
  /** Impide el salto de línea en la celda. */
  nowrap?: boolean;
  cardRole?: CardRole;
}

/**
 * Tabla de datos con **un solo patrón para toda la app**: tabla completa en
 * escritorio y una card por fila en móvil.
 *
 * El scroll horizontal se descarta a propósito como solución responsive: obliga a
 * descubrir que hay columnas escondidas y a arrastrar para leer un dato. La card
 * muestra lo mismo en vertical, que es la dimensión que sobra en un móvil.
 *
 * Vive como componente y no como receta repetida en cada pantalla para que las
 * cinco tablas de la app (usuarios, historiales EF/Scrum/Arquitectura, backlog)
 * se vean y se comporten igual, y para que arreglar algo aquí lo arregle en todas.
 */
export function DataTable<T>({
  columns,
  rows,
  rowKey,
  loading = false,
  skeletonRows = 4,
  empty = "No hay datos.",
  toolbar,
  zebra = false,
  footer,
  className,
}: {
  columns: DataColumn<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  loading?: boolean;
  skeletonRows?: number;
  empty?: React.ReactNode;
  /** Buscador y filtros, integrados en la cabecera del card de la tabla. */
  toolbar?: React.ReactNode;
  /** Franjas alternas: ayudan a seguir la fila en listas largas. */
  zebra?: boolean;
  footer?: React.ReactNode;
  className?: string;
}) {
  const vacia = !loading && rows.length === 0;

  const titleCol = columns.find((c) => c.cardRole === "title");
  const metaCols = columns.filter((c) => c.cardRole === "meta");
  const badgeCols = columns.filter((c) => c.cardRole === "badge");
  const actionsCol = columns.find((c) => c.cardRole === "actions");
  const pairCols = columns.filter(
    (c) => (c.cardRole ?? "pair") === "pair" && c !== titleCol,
  );

  return (
    <section className={cn("min-w-0", className)}>
      {/* Cabecera del card: buscador + filtros. Compartida por ambos tamaños. */}
      {toolbar && (
        <div className="mb-3 md:mb-0 md:rounded-t-xl md:border md:border-b-0 md:bg-muted/20 md:px-4 md:py-3">
          {toolbar}
        </div>
      )}

      {/* ---------- ESCRITORIO: tabla ---------- */}
      <div
        className={cn(
          "hidden overflow-hidden border bg-card shadow-sm md:block",
          toolbar ? "rounded-b-xl border-t-0" : "rounded-xl",
        )}
      >
        <table className="w-full border-collapse text-sm">
          <thead className="sticky top-0 z-[1] bg-muted/60 backdrop-blur supports-backdrop-filter:bg-muted/50">
            <tr className="border-b">
              {columns.map((col) => (
                <th
                  key={col.key}
                  scope="col"
                  className={cn(
                    // Tipografía de label: versalitas de 11px con tracking.
                    "px-4 py-2.5 text-[11px] font-semibold uppercase tracking-wide text-meta-foreground",
                    col.numeric ? "text-right" : "text-left",
                    col.width,
                  )}
                >
                  {col.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border/60">
            {loading ? (
              Array.from({ length: skeletonRows }).map((_, i) => (
                <tr key={`sk-${i}`}>
                  {columns.map((col) => (
                    <td key={col.key} className="px-4 py-3">
                      <div className="h-4 w-full max-w-28 animate-pulse rounded bg-muted" />
                    </td>
                  ))}
                </tr>
              ))
            ) : vacia ? (
              <tr>
                <td
                  colSpan={columns.length}
                  className="px-4 py-10 text-center text-sm text-muted-foreground"
                >
                  {empty}
                </td>
              </tr>
            ) : (
              rows.map((row) => (
                <tr
                  key={rowKey(row)}
                  className={cn(
                    "transition-colors hover:bg-primary/[0.04]",
                    zebra && "odd:bg-muted/20",
                  )}
                >
                  {columns.map((col) => (
                    <td
                      key={col.key}
                      className={cn(
                        // Altura cómoda: 12px verticales sobre un cuerpo de 13px.
                        "px-4 py-3 align-middle",
                        col.numeric && "text-right font-mono tabular-nums",
                        col.nowrap && "whitespace-nowrap",
                      )}
                    >
                      {col.render(row)}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
        {footer && (
          <div className="border-t bg-muted/20 px-4 py-2.5">{footer}</div>
        )}
      </div>

      {/* ---------- MÓVIL: una card por fila ---------- */}
      <div className="space-y-2 md:hidden">
        {loading ? (
          Array.from({ length: skeletonRows }).map((_, i) => (
            <div
              key={`skc-${i}`}
              className="h-28 animate-pulse rounded-xl bg-muted/50"
            />
          ))
        ) : vacia ? (
          <p className="rounded-xl border border-dashed px-4 py-8 text-center text-sm text-muted-foreground">
            {empty}
          </p>
        ) : (
          rows.map((row) => (
            <article
              key={rowKey(row)}
              className="rounded-xl border bg-card p-3 shadow-sm"
            >
              <div className="flex items-start gap-2">
                <div className="min-w-0 flex-1">
                  {titleCol && (
                    <div className="text-sm font-semibold leading-snug">
                      {titleCol.render(row)}
                    </div>
                  )}
                  {metaCols.map((col) => (
                    <div
                      key={col.key}
                      className="mt-0.5 truncate text-xs text-meta-foreground"
                    >
                      {col.render(row)}
                    </div>
                  ))}
                </div>
                {actionsCol && (
                  // Touch target: el contenedor reserva 44px de alto.
                  <div className="flex min-h-11 shrink-0 items-start">
                    {actionsCol.render(row)}
                  </div>
                )}
              </div>

              {badgeCols.length > 0 && (
                <div className="mt-2 flex flex-wrap items-center gap-1.5">
                  {badgeCols.map((col) => (
                    <span key={col.key}>{col.render(row)}</span>
                  ))}
                </div>
              )}

              {pairCols.length > 0 && (
                <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-2 border-t pt-2.5">
                  {pairCols.map((col) => (
                    <div key={col.key} className="min-w-0">
                      <dt className="text-[10px] font-semibold uppercase tracking-wide text-meta-foreground">
                        {col.label}
                      </dt>
                      <dd
                        className={cn(
                          "mt-0.5 truncate text-xs",
                          col.numeric && "font-mono tabular-nums",
                        )}
                      >
                        {col.render(row)}
                      </dd>
                    </div>
                  ))}
                </dl>
              )}
            </article>
          ))
        )}
        {footer && <div className="pt-1">{footer}</div>}
      </div>
    </section>
  );
}
