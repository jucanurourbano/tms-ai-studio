"use client";

import { Loader2 } from "lucide-react";
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
import { ALL_MODULES, MODULE_LABELS } from "@/lib/permissions";
import type { AccessLevel, AuthUser, RolesCatalog } from "@/lib/types/auth";

/** Valor del selector por módulo: sin grant, lectura o edición. */
type Choice = "none" | AccessLevel;

const CHOICE_LABEL: Record<Choice, string> = {
  none: "—",
  read: "Solo lectura",
  full: "Edición",
};

const SELECT_CLASS =
  "h-7 rounded-md border border-input bg-background px-2 text-xs shadow-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:opacity-50";

/**
 * Editor de **accesos adicionales** de un usuario (tabla `user_module_grants`).
 *
 * Los grants SUMAN sobre el rol y nunca restan, así que el editor muestra, junto
 * a cada módulo, lo que ya concede el rol: si el rol da Edición, un grant de
 * lectura no cambia nada y conviene que el administrador lo vea antes de
 * guardar. Guardar envía el conjunto COMPLETO (semántica de *replace* del
 * endpoint `PUT /auth/users/{id}/grants`).
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
  const [choices, setChoices] = useState<Record<string, Choice>>({});

  // Lo que concede el ROL del usuario (no editable aquí; es contexto).
  const porRol = useMemo<Record<string, AccessLevel | undefined>>(() => {
    const fila = catalog?.roles.find((r) => r.value === user.role);
    return fila?.modules ?? {};
  }, [catalog, user.role]);

  // Al abrir se parte del estado real del usuario.
  function abrir(abierto: boolean) {
    if (abierto) {
      const inicial: Record<string, Choice> = {};
      for (const modulo of ALL_MODULES) inicial[modulo] = "none";
      for (const g of user.grants) inicial[g.module] = g.level;
      setChoices(inicial);
    }
    onOpenChange(abierto);
  }

  async function guardar() {
    setSaving(true);
    try {
      const grants = ALL_MODULES.filter(
        (m) => choices[m] && choices[m] !== "none",
      ).map((m) => ({ module: m, level: choices[m] as AccessLevel }));
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
            Suman sobre lo que ya concede su rol; nunca restan. Deja «—» para no
            añadir nada en ese módulo.
          </DialogDescription>
        </DialogHeader>

        <div className="max-h-[50vh] divide-y divide-border/60 overflow-y-auto rounded-lg border">
          {ALL_MODULES.map((modulo) => {
            const rol = porRol[modulo];
            const elegido = choices[modulo] ?? "none";
            // Un grant que no supera lo del rol no aporta nada: se avisa.
            const redundante =
              rol === "full" || (rol === "read" && elegido === "read");
            return (
              <div
                key={modulo}
                className="flex items-center gap-3 px-3 py-2 text-sm"
              >
                <span className="min-w-0 flex-1 truncate">
                  {MODULE_LABELS[modulo]}
                </span>
                <span className="shrink-0 text-[11px] text-meta-foreground">
                  {rol ? `por rol: ${CHOICE_LABEL[rol]}` : "sin acceso por rol"}
                </span>
                <select
                  aria-label={`Acceso adicional a ${MODULE_LABELS[modulo]}`}
                  value={elegido}
                  disabled={saving}
                  onChange={(e) =>
                    setChoices((prev) => ({
                      ...prev,
                      [modulo]: e.target.value as Choice,
                    }))
                  }
                  className={SELECT_CLASS}
                >
                  <option value="none">—</option>
                  <option value="read">Solo lectura</option>
                  <option value="full">Edición</option>
                </select>
                {elegido !== "none" && redundante && (
                  <span
                    className="shrink-0 text-[11px] text-amber-600"
                    title="El rol ya concede este nivel o más; el acceso adicional no cambia nada."
                  >
                    sin efecto
                  </span>
                )}
              </div>
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
