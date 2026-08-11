"use client";

import { Boxes, Plus } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { NewSystemDialog } from "@/components/inventario/new-system-dialog";
import { SystemCard } from "@/components/inventario/system-card";
import { PageContainer } from "@/components/shell/page-container";
import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api/client";
import { inventarioApi } from "@/lib/api/inventario";
import { useAuth } from "@/lib/auth/auth-context";
import type { InventorySystem } from "@/lib/types/inventario";

/**
 * Inventario de Sistemas: lo que la organización YA tiene.
 *
 * Es la primera pantalla del módulo y la que instaura el hábito que justifica
 * todo el bloque: mirar qué existe antes de pedir que se construya.
 */
export default function InventarioPage() {
  const { can } = useAuth();
  const puedeEditar = can("inventario", "full");

  const [systems, setSystems] = useState<InventorySystem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [abrirAlta, setAbrirAlta] = useState(false);

  const cargar = useCallback(() => {
    inventarioApi
      .listSystems()
      .then((r) => {
        setSystems(r.items);
        setError(null);
      })
      .catch((err) =>
        setError(
          err instanceof ApiError
            ? err.message
            : "No se pudo cargar el inventario.",
        ),
      );
  }, []);

  useEffect(() => {
    cargar();
  }, [cargar]);

  return (
    <PageContainer className="animate-rise">
      <PageHeader
        module="inventario"
        icon="boxes"
        eyebrow="Conocimiento"
        title="Inventario de Sistemas"
        description="Los sistemas que ya existen y su contenido real. Es contra esto que los agentes de diseño reconcilian lo que proponen."
        action={
          puedeEditar ? (
            <Button size="sm" className="gap-1.5" onClick={() => setAbrirAlta(true)}>
              <Plus className="h-3.5 w-3.5" />
              Nuevo sistema
            </Button>
          ) : undefined
        }
      />

      {error && (
        <p className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </p>
      )}

      {systems === null && !error && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-36 w-full rounded-xl" />
          ))}
        </div>
      )}

      {systems?.length === 0 && (
        <div className="rounded-xl border border-dashed p-8 text-center">
          <Boxes className="mx-auto h-8 w-8 text-muted-foreground" />
          <p className="mt-3 text-sm font-medium">
            El inventario está vacío
          </p>
          <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
            Mientras no haya ningún sistema registrado, los agentes de diseño
            trabajan como si la organización partiera de cero: propondrán crear
            todo, incluso lo que ya existe en producción.
          </p>
          {puedeEditar && (
            <Button
              size="sm"
              className="mt-4 gap-1.5"
              onClick={() => setAbrirAlta(true)}
            >
              <Plus className="h-3.5 w-3.5" />
              Registrar el primer sistema
            </Button>
          )}
        </div>
      )}

      {systems && systems.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {systems.map((system) => (
            <SystemCard key={system.id} system={system} />
          ))}
        </div>
      )}

      {puedeEditar && (
        <NewSystemDialog
          open={abrirAlta}
          onOpenChange={setAbrirAlta}
          onCreated={(system) => {
            toast.success(`Sistema «${system.name}» registrado`);
            cargar();
          }}
        />
      )}
    </PageContainer>
  );
}
