"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { AssetPanel } from "@/components/inventario/asset-panel";
import { SystemDetailView } from "@/components/inventario/system-detail-view";
import { PageContainer } from "@/components/shell/page-container";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api/client";
import { inventarioApi } from "@/lib/api/inventario";
import type { InventoryAsset, InventorySystem } from "@/lib/types/inventario";

/**
 * Ficha de un sistema del inventario: sus activos por tipo y, al abrir uno, su
 * contenido en el panel lateral.
 *
 * Misma mecánica que el centro de comando de los artefactos (§5.1 de CLAUDE.md):
 * la lista es el índice y el contenido se explora en un panel, para que no haya
 * que abandonar la ficha para mirar una tabla.
 */
export default function InventarioSystemPage() {
  const params = useParams<{ systemId: string }>();
  const systemId = params.systemId;

  const [system, setSystem] = useState<InventorySystem | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [abierto, setAbierto] = useState<InventoryAsset | null>(null);

  const cargar = useCallback(() => {
    inventarioApi
      .getSystem(systemId)
      .then((s) => {
        setSystem(s);
        setError(null);
      })
      .catch((err) =>
        setError(
          err instanceof ApiError
            ? err.message
            : "No se pudo cargar el sistema.",
        ),
      )
      .finally(() => setLoading(false));
  }, [systemId]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  if (loading) {
    return (
      <PageContainer>
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-40 w-full" />
      </PageContainer>
    );
  }

  if (error || !system) {
    return (
      <PageContainer>
        <Card>
          <CardHeader>
            <CardTitle className="text-base text-red-600">
              No se pudo cargar el sistema
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <p className="text-muted-foreground">{error}</p>
            <Link href="/inventario">
              <Button variant="outline" size="sm" className="gap-1.5">
                <ArrowLeft className="h-3.5 w-3.5" />
                Volver al inventario
              </Button>
            </Link>
          </CardContent>
        </Card>
      </PageContainer>
    );
  }

  return (
    <>
      <SystemDetailView
        system={system}
        onReload={cargar}
        onOpenAsset={setAbierto}
      />
      <AssetPanel
        asset={abierto}
        onClose={() => setAbierto(null)}
        onChanged={cargar}
      />
    </>
  );
}
