"use client";

import { Layers, Loader2, XCircle } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { authApi } from "@/lib/api/auth";
import { ApiError } from "@/lib/api/client";
import {
  ALL_MODULES,
  FULLSTACK_MODULES,
  MODULE_LABELS,
} from "@/lib/permissions";
import type {
  AccessLevel,
  AuthUser,
  ModuleKey,
  RolesCatalog,
} from "@/lib/types/auth";
import { cn } from "@/lib/utils";

/** Selección en curso: módulo -> nivel concedido. Módulo ausente = sin grant. */
type Seleccion = Partial<Record<ModuleKey, AccessLevel>>;

const LEVEL_LABEL: Record<AccessLevel, string> = {
  read: "Solo lectura",
  full: "Edición",
};

/**
 * Editor de **accesos adicionales** de un usuario (tabla `user_module_grants`).
 *
 * Los módulos se marcan con **checkboxes múltiples** (varios de una pasada) en vez
 * de un desplegable por módulo: el caso real es "dale a esta persona Backend,
 * Frontend, BD y API", y hacerlo de a uno era el paso más tedioso del panel. De
 * ahí también el atajo **Full stack**, que marca esos cuatro de golpe.
 *
 * Al marcar, el nivel por defecto es **Edición** (quien recibe un módulo extra
 * suele necesitar trabajar en él); se puede bajar a Solo lectura por módulo.
 *
 * Los grants **SUMAN sobre el rol y nunca restan**: junto a cada módulo se
 * muestra lo que ya concede el rol y se marca "sin efecto" cuando lo elegido no
 * supera ese nivel. Guardar envía el conjunto COMPLETO (semántica de *replace*
 * del endpoint `PUT /auth/users/{id}/grants`).
 */
export function GrantsEditor({
  user,
  catalog,
  open,
  onOpenChange,
  onSaved,
}: {
  user: AuthUser;
  /** Catálogo del backend, para mostrar qué concede el rol. `null` si no cargó. */
  catalog: RolesCatalog | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSaved: () => void;
}) {
  const [saving, setSaving] = useState(false);
  const [seleccion, setSeleccion] = useState<Seleccion>({});

  // Lo que concede el ROL del usuario (contexto, no editable aquí).
  const porRol = useMemo<Partial<Record<string, AccessLevel>>>(() => {
    const fila = catalog?.roles.find((r) => r.value === user.role);
    return fila?.modules ?? {};
  }, [catalog, user.role]);

  // Al abrir se parte del estado real del usuario.
  function abrir(abierto: boolean) {
    if (abierto) {
      const inicial: Seleccion = {};
      for (const g of user.grants) inicial[g.module] = g.level;
      setSeleccion(inicial);
    }
    onOpenChange(abierto);
  }

  function toggle(modulo: ModuleKey) {
    setSeleccion((prev) => {
      const next = { ...prev };
      if (next[modulo]) delete next[modulo];
      else next[modulo] = "full"; // por defecto, Edición
      return next;
    });
  }

  function setNivel(modulo: ModuleKey, level: AccessLevel) {
    setSeleccion((prev) => ({ ...prev, [modulo]: level }));
  }

  /** Atajo: marca los cuatro módulos de construcción con Edición. */
  function marcarFullStack() {
    setSeleccion((prev) => {
      const next = { ...prev };
      for (const m of FULLSTACK_MODULES) next[m] = "full";
      return next;
    });
  }

  const total = Object.keys(seleccion).length;
  const fullStackCompleto = FULLSTACK_MODULES.every(
    (m) => seleccion[m] === "full",
  );

  async function guardar() {
    setSaving(true);
    try {
      const grants = (Object.keys(seleccion) as ModuleKey[]).map((m) => ({
        module: m,
        level: seleccion[m] as AccessLevel,
      }));
      await authApi.setGrants(user.id, grants);
      toast.success("Accesos adicionales actualizados");
      onOpenChange(false);
      onSaved();
    } catch (err) {
      toast.error("No se pudieron guardar los accesos", {
        description: err instanceof ApiError ? err.message : undefined,
      });
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={abrir}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Accesos adicionales · {user.full_name}</DialogTitle>
          <DialogDescription>
            Marca los módulos que quieras añadir. Suman sobre lo que ya concede su
            rol y nunca restan.
          </DialogDescription>
        </DialogHeader>

        {/* Atajos para el caso común */}
        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            variant={fullStackCompleto ? "secondary" : "outline"}
            size="sm"
            className="gap-1.5"
            disabled={saving}
            onClick={marcarFullStack}
            title="Marca Backend, Frontend, Base de datos y API con Edición"
          >
            <Layers className="h-3.5 w-3.5" />
            Full stack
          </Button>
          {total > 0 && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="gap-1.5"
              disabled={saving}
              onClick={() => setSeleccion({})}
            >
              <XCircle className="h-3.5 w-3.5" />
              Quitar todos
            </Button>
          )}
          <span className="ml-auto text-[11px] text-meta-foreground">
            {total === 0
              ? "Sin accesos adicionales"
              : `${total} módulo${total === 1 ? "" : "s"} seleccionado${
                  total === 1 ? "" : "s"
                }`}
          </span>
        </div>

        <div className="max-h-[50vh] divide-y divide-border/60 overflow-y-auto rounded-lg border">
          {ALL_MODULES.map((modulo) => {
            const rol = porRol[modulo];
            const nivel = seleccion[modulo];
            const marcado = nivel !== undefined;
            // Un grant que no supera lo del rol no aporta nada: se avisa.
            const sinEfecto =
              marcado && (rol === "full" || (rol === "read" && nivel === "read"));
            return (
              <label
                key={modulo}
                className={cn(
                  "flex cursor-pointer items-center gap-3 px-3 py-2 text-sm transition-colors hover:bg-primary/[0.03]",
                  marcado && "bg-primary/[0.04]",
                )}
              >
                <input
                  type="checkbox"
                  checked={marcado}
                  disabled={saving}
                  onChange={() => toggle(modulo)}
                  className="h-4 w-4 shrink-0 accent-primary"
                />
                <span className="min-w-0 flex-1 truncate">
                  {MODULE_LABELS[modulo]}
                </span>
                <span className="shrink-0 text-[11px] text-meta-foreground">
                  {rol ? `por rol: ${LEVEL_LABEL[rol]}` : "sin acceso por rol"}
                </span>
                {/* El nivel solo aplica al módulo marcado. `preventDefault` en el
                    click evita que interactuar con el select alterne el checkbox
                    del <label> que lo envuelve. */}
                <select
                  aria-label={`Nivel de acceso a ${MODULE_LABELS[modulo]}`}
                  value={nivel ?? "full"}
                  disabled={saving || !marcado}
                  onChange={(e) => setNivel(modulo, e.target.value as AccessLevel)}
                  onClick={(e) => e.preventDefault()}
                  className="h-7 shrink-0 rounded-md border border-input bg-background px-1.5 text-xs shadow-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:opacity-40"
                >
                  <option value="full">Edición</option>
                  <option value="read">Solo lectura</option>
                </select>
                <span className="w-16 shrink-0 text-right text-[11px] text-amber-600">
                  {sinEfecto ? "sin efecto" : ""}
                </span>
              </label>
            );
          })}
        </div>

        <DialogFooter>
          <Button onClick={guardar} disabled={saving} className="gap-2">
            {saving && <Loader2 className="h-4 w-4 animate-spin" />}
            Guardar accesos
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
