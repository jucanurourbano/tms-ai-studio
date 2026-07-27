"use client";

import { AlertTriangle, Loader2, ShieldOff, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
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
import { Label } from "@/components/ui/label";
import { PasswordInput } from "@/components/ui/password-input";
import { authApi } from "@/lib/api/auth";
import { ApiError } from "@/lib/api/client";
import type { AuthUser, UserActivity } from "@/lib/types/auth";

/** Restablecimiento de contraseña definido por un administrador. */
export function ResetPasswordDialog({
  user,
  open,
  onOpenChange,
}: {
  user: AuthUser;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [password, setPassword] = useState("");
  const [saving, setSaving] = useState(false);

  function handleOpenChange(next: boolean) {
    if (next) setPassword("");
    onOpenChange(next);
  }

  async function guardar(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      await authApi.resetPassword(user.id, password);
      toast.success("Contraseña restablecida", {
        description: `${user.full_name} deberá entrar con la contraseña nueva.`,
      });
      onOpenChange(false);
    } catch (err) {
      toast.error("No se pudo restablecer", {
        description: err instanceof ApiError ? err.message : undefined,
      });
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Restablecer contraseña</DialogTitle>
          <DialogDescription>
            Define una contraseña nueva para <b>{user.full_name}</b>. Comunícasela
            por un canal seguro; no se vuelve a mostrar.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={guardar} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="reset-password">Contraseña nueva</Label>
            <PasswordInput
              id="reset-password"
              value={password}
              onChange={setPassword}
              required
              minLength={8}
              autoComplete="new-password"
              placeholder="Mínimo 8 caracteres"
              disabled={saving}
            />
          </div>
          <DialogFooter>
            <Button
              type="submit"
              disabled={saving || password.length < 8}
              className="gap-2"
            >
              {saving && <Loader2 className="h-4 w-4 animate-spin" />}
              Restablecer
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** Confirmación de activar/desactivar. */
export function ToggleActiveDialog({
  user,
  open,
  onOpenChange,
  onDone,
}: {
  user: AuthUser;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onDone: () => void;
}) {
  const [saving, setSaving] = useState(false);
  const desactivando = user.is_active;

  async function confirmar() {
    setSaving(true);
    try {
      await authApi.setActive(user.id, !user.is_active);
      toast.success(desactivando ? "Usuario desactivado" : "Usuario reactivado");
      onOpenChange(false);
      onDone();
    } catch (err) {
      toast.error("No se pudo actualizar", {
        description: err instanceof ApiError ? err.message : undefined,
      });
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {desactivando ? "Desactivar usuario" : "Reactivar usuario"}
          </DialogTitle>
          <DialogDescription>
            {desactivando ? (
              <>
                <b>{user.full_name}</b> no podrá iniciar sesión. Su historial y sus
                asignaciones se conservan y la cuenta puede reactivarse cuando
                quieras.
              </>
            ) : (
              <>
                <b>{user.full_name}</b> volverá a poder iniciar sesión con sus
                credenciales actuales.
              </>
            )}
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button
            onClick={confirmar}
            disabled={saving}
            variant={desactivando ? "destructive" : "default"}
            className="gap-2"
          >
            {saving ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <ShieldOff className="h-4 w-4" />
            )}
            {desactivando ? "Desactivar" : "Reactivar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/**
 * Baja de un usuario, con **confirmación explícita** y aviso de actividad.
 *
 * Antes de permitir la baja se consulta la huella del usuario
 * (`GET /auth/users/{id}/activity`): si tiene jobs o validaciones a su nombre se
 * recomienda **desactivar** en vez de eliminar, y se ofrece ese camino en el
 * propio diálogo. La baja es lógica: la fila se conserva para no romper la
 * trazabilidad (así lo hace el backend), y eso se dice explícitamente.
 *
 * Además hay que escribir el nombre del usuario para confirmar: evita el clic
 * accidental en una acción que corta el acceso a una persona.
 */
export function DeleteUserDialog({
  user,
  open,
  onOpenChange,
  onDone,
  onPreferDeactivate,
}: {
  user: AuthUser;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onDone: () => void;
  onPreferDeactivate: () => void;
}) {
  const [activity, setActivity] = useState<UserActivity | null>(null);
  const [confirmText, setConfirmText] = useState("");
  const [saving, setSaving] = useState(false);

  // El reset va en el handler de apertura, no en el efecto: la convención del
  // proyecto prohíbe setState síncrono en el cuerpo de un efecto (renders en
  // cascada). El efecto solo consulta, y actualiza desde el callback async.
  function handleOpenChange(next: boolean) {
    if (next) {
      setActivity(null);
      setConfirmText("");
    }
    onOpenChange(next);
  }

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    authApi
      .userActivity(user.id)
      .then((a) => {
        if (!cancelled) setActivity(a);
      })
      .catch(() => {
        /* sin el resumen se sigue pudiendo dar de baja, solo sin el aviso */
      });
    return () => {
      cancelled = true;
    };
  }, [open, user.id]);

  const confirmado = confirmText.trim() === user.full_name.trim();

  async function confirmar() {
    setSaving(true);
    try {
      await authApi.deleteUser(user.id);
      toast.success("Usuario dado de baja", {
        description: "Su historial se conserva para mantener la trazabilidad.",
      });
      onOpenChange(false);
      onDone();
    } catch (err) {
      toast.error("No se pudo dar de baja", {
        description: err instanceof ApiError ? err.message : undefined,
      });
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Eliminar usuario</DialogTitle>
          <DialogDescription>
            Se da de baja a <b>{user.full_name}</b>: no podrá iniciar sesión ni
            aparecerá en los listados. La ficha se conserva para que su historial
            (análisis, validaciones y asignaciones) siga siendo trazable.
          </DialogDescription>
        </DialogHeader>

        {activity?.recommend_deactivate && (
          <div className="flex items-start gap-3 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <div className="min-w-0 flex-1">
              <p className="font-medium">Este usuario tiene actividad registrada</p>
              <p className="mt-0.5">
                {activity.jobs} análisis y {activity.validations} validaciones a su
                nombre. Se recomienda <b>desactivar</b> la cuenta: conserva el
                historial igual de legible y es reversible sin trámites.
              </p>
              <Button
                variant="outline"
                size="sm"
                className="mt-2 gap-1.5"
                onClick={() => {
                  onOpenChange(false);
                  onPreferDeactivate();
                }}
              >
                <ShieldOff className="h-3.5 w-3.5" />
                Desactivar en su lugar
              </Button>
            </div>
          </div>
        )}

        <div className="space-y-1.5">
          <Label htmlFor="confirm-delete">
            Escribe <b>{user.full_name}</b> para confirmar
          </Label>
          <input
            id="confirm-delete"
            value={confirmText}
            onChange={(e) => setConfirmText(e.target.value)}
            disabled={saving}
            autoComplete="off"
            className="flex h-8 w-full rounded-lg border border-input bg-background px-2.5 text-sm shadow-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:opacity-50"
          />
        </div>

        <DialogFooter>
          <Button
            variant="destructive"
            onClick={confirmar}
            disabled={saving || !confirmado}
            className="gap-2"
          >
            {saving ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Trash2 className="h-4 w-4" />
            )}
            Eliminar usuario
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
