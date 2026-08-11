"use client";

import { ChevronRight, KeyRound, Link2, Search } from "lucide-react";
import { useMemo, useState } from "react";

import { SearchInput } from "@/components/ui/search-input";
import { normalizeText } from "@/lib/artifact-search";
import type { DbSchemaContent, InventoryTable } from "@/lib/types/inventario";
import { cn } from "@/lib/utils";

/**
 * Vista del esquema de un activo `db_schema`: tablas plegadas que se expanden a
 * sus columnas.
 *
 * Se pliegan por defecto a propósito: un esquema real tiene decenas de tablas y
 * cientos de columnas, y desplegarlo entero convierte la pantalla en un muro de
 * texto donde no se encuentra nada. El buscador filtra por tabla Y por columna,
 * porque la pregunta habitual no es "¿existe la tabla envios?" sino "¿dónde está
 * guardado el número de guía?".
 */
export function SchemaView({ content }: { content: DbSchemaContent }) {
  const [query, setQuery] = useState("");
  const [abiertas, setAbiertas] = useState<Record<string, boolean>>({});

  // `content.tables ?? []` crearía un array NUEVO en cada render y el useMemo de
  // abajo no memoizaría nada.
  const tablas = useMemo(() => content.tables ?? [], [content.tables]);
  const filtradas = useMemo(() => {
    const q = normalizeText(query.trim());
    if (!q) return tablas;
    return tablas.filter(
      (t) =>
        normalizeText(t.name).includes(q) ||
        (t.comment && normalizeText(t.comment).includes(q)) ||
        t.columns.some((c) => normalizeText(c.name).includes(q)),
    );
  }, [tablas, query]);

  // Con búsqueda activa se expanden solas: si el usuario buscó una columna,
  // esconderla detrás de un clic más sería negarle justo lo que pidió.
  const buscando = query.trim().length > 0;

  if (tablas.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        Este activo no tiene tablas.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <SearchInput
          value={query}
          onChange={setQuery}
          placeholder="Buscar tabla o columna…"
          className="max-w-xs"
        />
        <span className="text-xs text-meta-foreground">
          {filtradas.length} de {tablas.length} tablas
          {content.engine ? ` · ${content.engine}` : ""}
        </span>
      </div>

      {filtradas.length === 0 && (
        <p className="flex items-center gap-2 rounded-md border border-dashed p-4 text-sm text-muted-foreground">
          <Search className="h-4 w-4" />
          Ninguna tabla ni columna coincide con «{query}».
        </p>
      )}

      <ul className="divide-y rounded-lg border">
        {filtradas.map((tabla) => (
          <TableRow
            key={`${tabla.schema_name ?? ""}.${tabla.name}`}
            tabla={tabla}
            abierta={buscando || (abiertas[tabla.name] ?? false)}
            onToggle={() =>
              setAbiertas((prev) => ({
                ...prev,
                [tabla.name]: !(prev[tabla.name] ?? false),
              }))
            }
            resaltar={query.trim()}
          />
        ))}
      </ul>
    </div>
  );
}

function TableRow({
  tabla,
  abierta,
  onToggle,
  resaltar,
}: {
  tabla: InventoryTable;
  abierta: boolean;
  onToggle: () => void;
  resaltar: string;
}) {
  const q = normalizeText(resaltar);
  return (
    <li>
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={abierta}
        className="flex w-full items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-muted/50"
      >
        <ChevronRight
          className={cn(
            "h-4 w-4 shrink-0 text-muted-foreground transition-transform",
            abierta && "rotate-90",
          )}
        />
        <span className="font-mono text-sm font-medium">{tabla.name}</span>
        <span className="text-xs text-meta-foreground">
          {tabla.columns.length} columnas
        </span>
        {tabla.foreign_keys.length > 0 && (
          <span className="flex items-center gap-1 text-xs text-meta-foreground">
            <Link2 className="h-3 w-3" />
            {tabla.foreign_keys.length}
          </span>
        )}
        {tabla.comment && (
          <span className="ml-auto hidden truncate text-xs text-muted-foreground sm:block">
            {tabla.comment}
          </span>
        )}
      </button>

      {abierta && (
        <div className="overflow-x-auto border-t bg-muted/20 px-3 py-2">
          <table className="w-full min-w-[32rem] text-xs">
            <thead className="text-meta-foreground">
              <tr className="text-left">
                <th className="py-1 pr-3 font-medium">Columna</th>
                <th className="py-1 pr-3 font-medium">Tipo</th>
                <th className="py-1 pr-3 font-medium">Nulo</th>
                <th className="py-1 font-medium">Notas</th>
              </tr>
            </thead>
            <tbody>
              {tabla.columns.map((col) => (
                <tr
                  key={col.name}
                  className={cn(
                    "border-t border-border/40",
                    q && normalizeText(col.name).includes(q) && "bg-amber-50",
                  )}
                >
                  <td className="py-1 pr-3 font-mono">
                    <span className="inline-flex items-center gap-1">
                      {col.primary_key && (
                        <KeyRound className="h-3 w-3 text-amber-600" />
                      )}
                      {col.name}
                    </span>
                  </td>
                  <td className="py-1 pr-3 font-mono text-muted-foreground">
                    {col.type}
                  </td>
                  <td className="py-1 pr-3 text-muted-foreground">
                    {col.nullable ? "sí" : "no"}
                  </td>
                  <td className="py-1 text-muted-foreground">
                    {col.comment ?? ""}
                    {col.default ? ` · default ${col.default}` : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {tabla.foreign_keys.length > 0 && (
            <div className="mt-2 space-y-0.5 text-xs text-muted-foreground">
              {tabla.foreign_keys.map((fk, i) => (
                <p key={fk.name ?? i} className="font-mono">
                  {fk.columns.join(", ")} → {fk.referenced_table}(
                  {fk.referenced_columns.join(", ")})
                  {fk.on_delete ? ` ON DELETE ${fk.on_delete}` : ""}
                </p>
              ))}
            </div>
          )}
        </div>
      )}
    </li>
  );
}
