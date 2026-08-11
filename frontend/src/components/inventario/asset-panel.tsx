"use client";

import { History, Loader2, ShieldCheck } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { ApiError } from "@/lib/api/client";
import { inventarioApi } from "@/lib/api/inventario";
import { useAuth } from "@/lib/auth/auth-context";
import type { DbSchemaContent, InventoryAsset } from "@/lib/types/inventario";

import { SchemaView } from "./schema-view";

/**
 * Panel lateral con el contenido de un activo.
 *
 * El contenido NO viaja en el listado (un esquema real son cientos de KB): se
 * pide al abrir. Por eso el panel tiene su propio estado de carga.
 */
export function AssetPanel({
  asset,
  onClose,
  onChanged,
}: {
  asset: InventoryAsset | null;
  onClose: () => void;
  onChanged: () => void;
}) {
  return (
    <Sheet open={asset !== null} onOpenChange={(open) => !open && onClose()}>
      <SheetContent className="w-full sm:max-w-3xl">
        {/* `key` por activo: al cambiar de activo el cuerpo se REMONTA y su
            estado (contenido, versiones) se reinicia solo. Resetearlo a mano
            desde un efecto sería una cascada de renders evitable. */}
        {asset && (
          <AssetPanelBody key={asset.id} asset={asset} onChanged={onChanged} />
        )}
      </SheetContent>
    </Sheet>
  );
}

function AssetPanelBody({
  asset,
  onChanged,
}: {
  asset: InventoryAsset;
  onChanged: () => void;
}) {
  const { can } = useAuth();
  const puedeEditar = can("inventario", "full");

  const [completo, setCompleto] = useState<InventoryAsset | null>(null);
  const [versiones, setVersiones] = useState<InventoryAsset[] | null>(null);
  const [verVersiones, setVerVersiones] = useState(false);
  const [guardando, setGuardando] = useState(false);

  const assetId = asset.id;

  useEffect(() => {
    let vigente = true;
    inventarioApi
      .getAsset(assetId)
      .then((a) => {
        if (vigente) setCompleto(a);
      })
      .catch((err) =>
        toast.error(
          err instanceof ApiError
            ? err.message
            : "No se pudo cargar el activo.",
        ),
      );
    return () => {
      vigente = false;
    };
  }, [assetId]);

  const cargarVersiones = useCallback(() => {
    if (!assetId) return;
    setVerVersiones(true);
    inventarioApi
      .listVersions(assetId)
      .then((r) => setVersiones(r.items))
      .catch(() => setVersiones([]));
  }, [assetId]);

  async function marcarValidado() {
    if (!completo) return;
    setGuardando(true);
    try {
      const nuevo =
        completo.validation_status === "validado" ? "importado" : "validado";
      await inventarioApi.setAssetStatus(completo.id, nuevo);
      setCompleto({ ...completo, validation_status: nuevo });
      onChanged();
      toast.success(
        nuevo === "validado"
          ? "Activo marcado como validado"
          : "Activo devuelto a importado",
      );
    } catch (err) {
      toast.error(
        err instanceof ApiError ? err.message : "No se pudo actualizar.",
      );
    } finally {
      setGuardando(false);
    }
  }

  const esEsquema = asset.asset_type === "db_schema";

  return (
    <>
      <SheetHeader>
        <SheetTitle>{asset.name}</SheetTitle>
        <SheetDescription>
          v{asset.version} · {asset.origin_ref ?? asset.origin}
        </SheetDescription>
      </SheetHeader>

      <SheetBody className="space-y-4">
          {puedeEditar && completo && (
            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                variant="outline"
                className="gap-1.5"
                onClick={marcarValidado}
                disabled={guardando}
              >
                {guardando ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <ShieldCheck className="h-3.5 w-3.5" />
                )}
                {completo.validation_status === "validado"
                  ? "Marcar como importado"
                  : "Marcar como validado"}
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="gap-1.5"
                onClick={cargarVersiones}
              >
                <History className="h-3.5 w-3.5" />
                Ver versiones
              </Button>
            </div>
          )}

          {completo?.validation_status === "importado" && (
            <p className="rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-800">
              Este activo está <strong>importado pero sin revisar</strong>. La
              fase RECONCILE de los agentes de diseño decide contra este
              contenido.
            </p>
          )}

          {verVersiones && (
            <div className="rounded-md border">
              <p className="border-b px-3 py-2 text-xs font-semibold">
                Historial de versiones
              </p>
              {versiones === null ? (
                <p className="px-3 py-2 text-xs text-muted-foreground">
                  Cargando…
                </p>
              ) : (
                <ul className="divide-y text-xs">
                  {versiones.map((v) => (
                    <li
                      key={v.id}
                      className="flex items-center gap-2 px-3 py-1.5"
                    >
                      <span className="font-mono">v{v.version}</span>
                      <span className="text-muted-foreground">
                        {v.origin_ref ?? v.origin}
                      </span>
                      <span className="ml-auto text-meta-foreground">
                        {v.created_at?.slice(0, 10)}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {!completo && (
            <p className="text-sm text-muted-foreground">Cargando contenido…</p>
          )}

          {completo && esEsquema && (
            <SchemaView content={completo.content as DbSchemaContent} />
          )}

        {completo && !esEsquema && (
          <pre className="max-h-[60vh] overflow-auto rounded-md bg-muted p-3 text-xs">
            {JSON.stringify(completo.content, null, 2)}
          </pre>
        )}
      </SheetBody>
    </>
  );
}
