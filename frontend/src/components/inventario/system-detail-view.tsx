"use client";

import { ArrowLeft, ChevronRight, FileUp, Upload } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { PageContainer } from "@/components/shell/page-container";
import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth/auth-context";
import type {
  AssetType,
  InventoryAsset,
  InventorySystem,
} from "@/lib/types/inventario";
import { cn } from "@/lib/utils";

import { UploadDialog } from "./upload-dialog";
import {
  ASSET_LABEL,
  AssetTypeIcon,
  KIND_LABEL,
  STATUS_LABEL,
} from "./system-card";

const ORDEN: AssetType[] = ["db_schema", "module", "api", "document"];

const ORIGIN_LABEL: Record<string, string> = {
  ddl_dump: "dump DDL",
  introspection: "introspección",
  document: "documento",
  manual: "manual",
  isdf: "generado por ISDF",
};

export function SystemDetailView({
  system,
  onReload,
  onOpenAsset,
}: {
  system: InventorySystem;
  onReload: () => void;
  onOpenAsset: (asset: InventoryAsset) => void;
}) {
  const { can } = useAuth();
  const puedeEditar = can("inventario", "full");
  const [subir, setSubir] = useState<"ddl" | "document" | null>(null);

  const assets = system.assets ?? [];
  const porTipo = ORDEN.map((tipo) => ({
    tipo,
    items: assets.filter((a) => a.asset_type === tipo),
  })).filter((g) => g.items.length > 0);

  return (
    <PageContainer className="animate-rise">
      <Link
        href="/inventario"
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        Inventario
      </Link>

      <PageHeader
        module="inventario"
        icon="boxes"
        eyebrow={`${KIND_LABEL[system.kind]} · ${STATUS_LABEL[system.status]}`}
        title={system.name}
        description={system.description ?? undefined}
        action={
          puedeEditar ? (
            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                variant="outline"
                className="gap-1.5"
                onClick={() => setSubir("ddl")}
              >
                <Upload className="h-3.5 w-3.5" />
                Subir DDL
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="gap-1.5"
                onClick={() => setSubir("document")}
              >
                <FileUp className="h-3.5 w-3.5" />
                Subir documento
              </Button>
            </div>
          ) : undefined
        }
      />

      {assets.length === 0 && (
        <div className="rounded-xl border border-dashed p-8 text-center">
          <p className="text-sm font-medium">Este sistema no tiene activos</p>
          <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
            Sube un dump DDL para inventariar su esquema de datos, o un documento
            para extraer sus módulos y entidades. Sin activos, la fase RECONCILE
            no tiene nada contra lo que comparar.
          </p>
        </div>
      )}

      {porTipo.map(({ tipo, items }) => (
        <section key={tipo} className="space-y-2">
          <h2 className="flex items-center gap-2 text-sm font-semibold">
            <AssetTypeIcon type={tipo} className="h-4 w-4 text-stone-600" />
            {ASSET_LABEL[tipo]}
            <span className="text-xs font-normal text-meta-foreground">
              {items.length}
            </span>
          </h2>
          <ul className="divide-y rounded-lg border">
            {items.map((asset) => (
              <li key={asset.id}>
                <button
                  type="button"
                  onClick={() => onOpenAsset(asset)}
                  className="flex w-full items-center gap-3 px-3 py-2.5 text-left transition-colors hover:bg-muted/50"
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">{asset.name}</p>
                    <p className="text-xs text-meta-foreground">
                      v{asset.version} ·{" "}
                      {ORIGIN_LABEL[asset.origin] ?? asset.origin}
                      {asset.origin_ref ? ` · ${asset.origin_ref}` : ""}
                    </p>
                  </div>
                  <AssetSummaryChip asset={asset} />
                  <ValidationChip status={asset.validation_status} />
                  <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
                </button>
              </li>
            ))}
          </ul>
        </section>
      ))}

      {puedeEditar && subir && (
        <UploadDialog
          systemId={system.id}
          kind={subir}
          open
          onOpenChange={(open) => !open && setSubir(null)}
          onUploaded={() => {
            onReload();
            setSubir(null);
          }}
        />
      )}
    </PageContainer>
  );
}

function AssetSummaryChip({ asset }: { asset: InventoryAsset }) {
  const s = asset.summary;
  if (!s) return null;
  const partes: string[] = [];
  if (s.tables !== undefined) partes.push(`${s.tables} tablas`);
  if (s.columns !== undefined) partes.push(`${s.columns} columnas`);
  if (s.endpoints !== undefined) partes.push(`${s.endpoints} endpoints`);
  if (s.entities !== undefined) partes.push(`${s.entities} entidades`);
  if (s.functionalities !== undefined)
    partes.push(`${s.functionalities} funcionalidades`);
  if (partes.length === 0) return null;
  return (
    <span className="hidden text-xs text-muted-foreground sm:block">
      {partes.join(" · ")}
    </span>
  );
}

/**
 * Importado vs validado.
 *
 * No es decorativo: RECONCILE decide contra este contenido, y reutilizar una
 * tabla que un parser dedujo mal y nadie revisó es peor que no tener el dato.
 */
function ValidationChip({ status }: { status: string }) {
  const validado = status === "validado";
  return (
    <span
      title={
        validado
          ? "Alguien revisó este activo."
          : "Cargado pero SIN revisar. RECONCILE decide contra esto."
      }
      className={cn(
        "hidden rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ring-1 md:inline",
        validado
          ? "bg-emerald-100 text-emerald-700 ring-emerald-200"
          : "bg-amber-100 text-amber-700 ring-amber-200",
      )}
    >
      {validado ? "Validado" : "Importado"}
    </span>
  );
}
