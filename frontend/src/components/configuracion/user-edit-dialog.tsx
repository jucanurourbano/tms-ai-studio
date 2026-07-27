"use client";

import { Loader2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { NativeSelect } from "@/components/ui/native-select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { authApi } from "@/lib/api/auth";
import { ApiError } from "@/lib/api/client";
import {
  ALL_ROLES,
  ALL_SPECIALTIES,
  ROLE_LABELS,
  SPECIALTY_LABELS,
} from "@/lib/permissions";
import type { AuthUser, Specialty, UserRole } from "@/lib/types/auth";

/**
 * Edición de un usuario: identidad, rol y perfil de equipo.
 *
 * El **rol** se guarda por su propio endpoint (`PATCH …/role`, que exige rol
 * admin estricto) y el resto por `PATCH …/profile` (módulo `config`). Se envían
 * en dos llamadas porque son dos permisos distintos: así un gestor con `config`
 * puede corregir un nombre sin poder tocar roles.
 *
 * Los accesos adicionales (grants) se editan aparte, en su propio diálogo.
 */
export function UserEditDialog({
  user,
  open,
  onOpenChange,
  canEditRole,
  isSelf,
  onSaved,
}: {
  user: AuthUser;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Solo un admin puede cambiar roles. */
  canEditRole: boolean;
  isSelf: boolean;
  onSaved: () => void;
}) {
  const [fullName, setFullName] = useState(user.full_name);
  const [email, setEmail] = useState(user.email);
  const [institutional, setInstitutional] = useState(
    user.institutional_email ?? "",
  );
  const [specialty, setSpecialty] = useState<Specialty | "">(
    user.specialty ?? "",
  );
  const [available, setAvailable] = useState(user.available_for_assignment);
  const [role, setRole] = useState<UserRole>(user.role);
  const [saving, setSaving] = useState(false);

  // Al reabrir, el formulario debe reflejar el estado real del usuario.
  function handleOpenChange(next: boolean) {
    if (next) {
      setFullName(user.full_name);
      setEmail(user.email);
      setInstitutional(user.institutional_email ?? "");
      setSpecialty(user.specialty ?? "");
      setAvailable(user.available_for_assignment);
      setRole(user.role);
    }
    onOpenChange(next);
  }

  async function guardar(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      await authApi.updateProfile(user.id, {
        full_name: fullName.trim(),
        email: email.trim(),
        // Cadena vacía = borrar el institucional (vuelve a usarse el de acceso).
        institutional_email: institutional.trim(),
        // "" = sin especialidad declarada (se envía null).
        specialty: specialty === "" ? null : specialty,
        available_for_assignment: available,
      });
      if (canEditRole && !isSelf && role !== user.role) {
        await authApi.setRole(user.id, role);
      }
      toast.success("Usuario actualizado");
      onOpenChange(false);
      onSaved();
    } catch (err) {
      toast.error("No se pudo guardar", {
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
          <DialogTitle>Editar usuario</DialogTitle>
          <DialogDescription>
            Datos de acceso, rol y perfil de equipo para la asignación de
            historias.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={guardar} className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="edit-name">Nombre completo</Label>
              <Input
                id="edit-name"
                required
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                disabled={saving}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="edit-email">Correo de acceso</Label>
              <Input
                id="edit-email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={saving}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="edit-inst">Correo institucional</Label>
              <Input
                id="edit-inst"
                type="email"
                value={institutional}
                onChange={(e) => setInstitutional(e.target.value)}
                placeholder={user.email}
                disabled={saving}
              />
              <p className="text-[11px] text-meta-foreground">
                El que se exporta a ClickUp. Vacío = se usa el de acceso.
              </p>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="edit-specialty">Especialidad</Label>
              <NativeSelect
                id="edit-specialty"
                value={specialty}
                disabled={saving}
                onChange={(e) => setSpecialty(e.target.value as Specialty | "")}
              >
                <option value="">Sin especificar</option>
                {ALL_SPECIALTIES.map((s) => (
                  <option key={s} value={s}>
                    {SPECIALTY_LABELS[s]}
                  </option>
                ))}
              </NativeSelect>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="edit-role">Rol</Label>
              <NativeSelect
                id="edit-role"
                value={role}
                disabled={saving || !canEditRole || isSelf}
                onChange={(e) => setRole(e.target.value as UserRole)}
              >
                {ALL_ROLES.map((r) => (
                  <option key={r} value={r}>
                    {ROLE_LABELS[r]}
                  </option>
                ))}
              </NativeSelect>
              {isSelf && (
                <p className="text-[11px] text-meta-foreground">
                  No puedes cambiar tu propio rol.
                </p>
              )}
              {!canEditRole && !isSelf && (
                <p className="text-[11px] text-meta-foreground">
                  Solo un Administrador cambia roles.
                </p>
              )}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="edit-available">Disponible para asignación</Label>
              <NativeSelect
                id="edit-available"
                value={available ? "si" : "no"}
                disabled={saving}
                onChange={(e) => setAvailable(e.target.value === "si")}
              >
                <option value="si">Sí, aparece en «Asignar a»</option>
                <option value="no">No asignable</option>
              </NativeSelect>
            </div>
          </div>

          <DialogFooter>
            <Button type="submit" disabled={saving} className="gap-2">
              {saving && <Loader2 className="h-4 w-4 animate-spin" />}
              Guardar cambios
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
