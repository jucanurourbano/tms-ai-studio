"use client";

import { Boxes, Database, FileText, Plug, Puzzle } from "lucide-react";
import Link from "next/link";

import { Card, CardContent } from "@/components/ui/card";
import type {
  AssetType,
  InventorySystem,
  SystemKind,
  SystemStatus,
} from "@/lib/types/inventario";
import { cn } from "@/lib/utils";

/** Papel del sistema. El destino es el que reconcilian los agentes: se distingue. */
export const KIND_LABEL: Record<SystemKind, string> = {
  destino: "Destino",
  legado: "Legado",
  externo: "Externo",
};

const KIND_STYLE: Record<SystemKind, string> = {
  destino: "bg-emerald-100 text-emerald-700 ring-emerald-200",
  legado: "bg-amber-100 text-amber-700 ring-amber-200",
  externo: "bg-slate-100 text-slate-700 ring-slate-200",
};

export const STATUS_LABEL: Record<SystemStatus, string> = {
  en_construccion: "En construcción",
  activo: "Activo",
  en_migracion: "En migración",
  retirado: "Retirado",
};

export const ASSET_LABEL: Record<AssetType, string> = {
  db_schema: "Esquemas",
  module: "Módulos",
  api: "APIs",
  document: "Documentos",
};

export function AssetTypeIcon({
  type,
  className,
}: {
  type: AssetType;
  className?: string;
}) {
  if (type === "db_schema") return <Database className={className} />;
  if (type === "module") return <Puzzle className={className} />;
  if (type === "api") return <Plug className={className} />;
  return <FileText className={className} />;
}

export function SystemCard({ system }: { system: InventorySystem }) {
  const conteos = system.asset_counts ?? {};
  const total = Object.values(conteos).reduce((a, b) => a + (b ?? 0), 0);

  return (
    <Link
      href={`/inventario/${system.id}`}
      className="group block focus-visible:outline-none"
    >
      <Card className="h-full transition-shadow hover:shadow-md focus-within:ring-2 focus-within:ring-ring">
        <CardContent className="space-y-3 p-4">
          <div className="flex items-start gap-2">
            <span className="rounded-lg bg-gradient-to-br from-stone-100 to-stone-50 p-2 text-stone-700">
              <Boxes className="h-4 w-4" />
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate font-medium group-hover:text-stone-700">
                {system.name}
              </p>
              <p className="text-xs text-meta-foreground">
                {STATUS_LABEL[system.status]}
              </p>
            </div>
            <span
              className={cn(
                "rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ring-1",
                KIND_STYLE[system.kind],
              )}
            >
              {KIND_LABEL[system.kind]}
            </span>
          </div>

          {system.description && (
            <p className="line-clamp-2 text-xs text-muted-foreground">
              {system.description}
            </p>
          )}

          {total === 0 ? (
            <p className="text-xs text-muted-foreground">
              Sin activos cargados todavía.
            </p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {(Object.keys(conteos) as AssetType[]).map((tipo) => (
                <span
                  key={tipo}
                  className="inline-flex items-center gap-1 rounded-md bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground"
                >
                  <AssetTypeIcon type={tipo} className="h-3 w-3" />
                  {conteos[tipo]} {ASSET_LABEL[tipo].toLowerCase()}
                </span>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </Link>
  );
}
