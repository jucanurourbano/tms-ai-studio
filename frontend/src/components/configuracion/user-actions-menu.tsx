"use client";

import {
  KeyRound,
  MoreVertical,
  Pencil,
  ShieldCheck,
  ShieldOff,
  SlidersHorizontal,
  Trash2,
} from "lucide-react";
import { useState } from "react";

import { GrantsEditor } from "@/components/configuracion/grants-editor";
import {
  DeleteUserDialog,
  ResetPasswordDialog,
  ToggleActiveDialog,
} from "@/components/configuracion/user-danger-dialogs";
import { UserEditDialog } from "@/components/configuracion/user-edit-dialog";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { AuthUser, RolesCatalog } from "@/lib/types/auth";

/**
 * Menú kebab (⋮) con todas las acciones de un usuario.
 *
 * Van en un menú y no como botones en la fila para que la tabla no se sature:
 * son cinco acciones, dos de ellas destructivas. Cada una abre su diálogo, y las
 * que el actor no puede ejecutar (cambiar rol/accesos sin ser admin, actuar sobre
 * su propia cuenta) se deshabilitan con el motivo en el `title` en vez de
 * desaparecer, para que se entienda que existen.
 */
export function UserActionsMenu({
  user,
  catalog,
  isAdmin,
  isSelf,
  onChanged,
}: {
  user: AuthUser;
  catalog: RolesCatalog | null;
  isAdmin: boolean;
  isSelf: boolean;
  onChanged: () => void;
}) {
  const [editOpen, setEditOpen] = useState(false);
  const [grantsOpen, setGrantsOpen] = useState(false);
  const [resetOpen, setResetOpen] = useState(false);
  const [toggleOpen, setToggleOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger
          render={
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label={`Acciones de ${user.full_name}`}
            >
              <MoreVertical />
            </Button>
          }
        />
        <DropdownMenuContent>
          <DropdownMenuItem onClick={() => setEditOpen(true)}>
            <Pencil />
            Editar
          </DropdownMenuItem>
          <DropdownMenuItem
            disabled={!isAdmin || isSelf}
            title={
              isSelf
                ? "Un administrador no edita sus propios accesos"
                : !isAdmin
                  ? "Solo un Administrador gestiona accesos adicionales"
                  : undefined
            }
            onClick={() => setGrantsOpen(true)}
          >
            <SlidersHorizontal />
            Accesos adicionales
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => setResetOpen(true)}>
            <KeyRound />
            Restablecer contraseña
          </DropdownMenuItem>

          <DropdownMenuSeparator />

          <DropdownMenuItem
            disabled={isSelf && user.is_active}
            title={
              isSelf && user.is_active
                ? "No puedes desactivar tu propia cuenta"
                : undefined
            }
            onClick={() => setToggleOpen(true)}
          >
            {user.is_active ? <ShieldOff /> : <ShieldCheck />}
            {user.is_active ? "Desactivar" : "Reactivar"}
          </DropdownMenuItem>
          <DropdownMenuItem
            variant="destructive"
            disabled={isSelf}
            title={isSelf ? "No puedes eliminar tu propia cuenta" : undefined}
            onClick={() => setDeleteOpen(true)}
          >
            <Trash2 />
            Eliminar
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <UserEditDialog
        user={user}
        open={editOpen}
        onOpenChange={setEditOpen}
        canEditRole={isAdmin}
        isSelf={isSelf}
        onSaved={onChanged}
      />
      <GrantsEditor
        user={user}
        catalog={catalog}
        open={grantsOpen}
        onOpenChange={setGrantsOpen}
        onSaved={onChanged}
      />
      <ResetPasswordDialog
        user={user}
        open={resetOpen}
        onOpenChange={setResetOpen}
      />
      <ToggleActiveDialog
        user={user}
        open={toggleOpen}
        onOpenChange={setToggleOpen}
        onDone={onChanged}
      />
      <DeleteUserDialog
        user={user}
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        onDone={onChanged}
        // Si el usuario tiene actividad, el diálogo ofrece desactivar en su
        // lugar y salta directamente a esa confirmación.
        onPreferDeactivate={() => setToggleOpen(true)}
      />
    </>
  );
}
