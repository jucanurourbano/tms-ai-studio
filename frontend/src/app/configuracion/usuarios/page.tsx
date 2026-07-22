"use client";

import { Loader2, ShieldAlert, UserPlus } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/shell/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { authApi } from "@/lib/api/auth";
import { ApiError } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/auth-context";
import { absoluteTime, relativeTime } from "@/lib/format";
import type { AuthUser, UserRole } from "@/lib/types/auth";

function RoleBadge({ role }: { role: UserRole }) {
  return role === "admin" ? (
    <Badge
      variant="outline"
      className="border-violet-300 bg-violet-50 text-violet-700"
    >
      Administrador
    </Badge>
  ) : (
    <Badge variant="outline" className="text-muted-foreground">
      Miembro
    </Badge>
  );
}

function ActiveBadge({ active }: { active: boolean }) {
  return active ? (
    <Badge
      variant="outline"
      className="border-emerald-300 bg-emerald-50 text-emerald-700"
    >
      Activo
    </Badge>
  ) : (
    <Badge variant="outline" className="border-red-300 bg-red-50 text-red-700">
      Inactivo
    </Badge>
  );
}

export default function UsuariosPage() {
  const { user: current, isAdmin } = useAuth();
  const [users, setUsers] = useState<AuthUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Formulario de alta.
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<UserRole>("member");
  const [submitting, setSubmitting] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);

  // El estado se actualiza solo en callbacks async (convención del proyecto:
  // nunca setState síncrono dentro de un efecto). ``loading`` arranca en true.
  const fetchUsers = useCallback(() => {
    authApi
      .listUsers(100, 0)
      .then((d) => {
        setUsers(d.items);
        setError(null);
      })
      .catch((err) =>
        setError(
          err instanceof ApiError ? err.message : "No se pudo cargar la lista.",
        ),
      )
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (isAdmin) fetchUsers();
  }, [isAdmin, fetchUsers]);

  async function onRegister(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      await authApi.register({ email, full_name: fullName, password, role });
      toast.success("Usuario registrado");
      setFullName("");
      setEmail("");
      setPassword("");
      setRole("member");
      fetchUsers();
    } catch (err) {
      toast.error(
        err instanceof ApiError ? err.message : "No se pudo registrar el usuario.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  async function onToggleActive(u: AuthUser) {
    setBusyId(u.id);
    try {
      await authApi.setActive(u.id, !u.is_active);
      toast.success(u.is_active ? "Usuario desactivado" : "Usuario reactivado");
      fetchUsers();
    } catch (err) {
      toast.error(
        err instanceof ApiError ? err.message : "No se pudo actualizar el usuario.",
      );
    } finally {
      setBusyId(null);
    }
  }

  if (!isAdmin) {
    return (
      <div className="mx-auto max-w-2xl p-6">
        <div className="flex items-start gap-3 rounded-xl border border-amber-300 bg-amber-50 p-4 text-amber-800">
          <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0" />
          <div>
            <h1 className="font-heading text-base font-semibold">
              Acceso restringido
            </h1>
            <p className="mt-1 text-sm">
              Solo los administradores pueden gestionar usuarios.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl p-6">
      <PageHeader
        eyebrow="Configuración"
        title="Usuarios"
        description="Administra el acceso a TMS AI Studio: registra usuarios y activa o desactiva cuentas."
      />

      {/* Alta de usuario */}
      <Card className="mb-6">
        <div className="px-(--card-spacing)">
          <h2 className="font-heading text-base font-semibold">
            Registrar usuario
          </h2>
          <form
            onSubmit={onRegister}
            className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4"
          >
            <div className="space-y-1.5">
              <Label htmlFor="fullName">Nombre completo</Label>
              <Input
                id="fullName"
                required
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder="Nombre Apellido"
                disabled={submitting}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="newEmail">Correo</Label>
              <Input
                id="newEmail"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="nombre@urbano.com.pe"
                disabled={submitting}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="newPassword">Contraseña</Label>
              <Input
                id="newPassword"
                type="password"
                required
                minLength={8}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Mínimo 8 caracteres"
                disabled={submitting}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="newRole">Rol</Label>
              <select
                id="newRole"
                value={role}
                onChange={(e) => setRole(e.target.value as UserRole)}
                disabled={submitting}
                className="flex h-8 w-full rounded-lg border border-input bg-background px-2.5 text-sm shadow-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:opacity-50"
              >
                <option value="member">Miembro</option>
                <option value="admin">Administrador</option>
              </select>
            </div>
            <div className="sm:col-span-2 lg:col-span-4">
              <Button
                type="submit"
                className="gap-2"
                disabled={submitting || !fullName || !email || password.length < 8}
              >
                {submitting ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <UserPlus className="h-4 w-4" />
                )}
                Registrar
              </Button>
            </div>
          </form>
        </div>
      </Card>

      {/* Listado */}
      {error && (
        <div className="mb-4 rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="overflow-x-auto rounded-md border">
        <Table className="min-w-[46rem]">
          <TableHeader className="bg-muted/60">
            <TableRow className="hover:bg-transparent">
              <TableHead>Nombre</TableHead>
              <TableHead>Correo</TableHead>
              <TableHead>Rol</TableHead>
              <TableHead>Estado</TableHead>
              <TableHead>Registrado</TableHead>
              <TableHead className="text-right">Acción</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody className="[&_tr:nth-child(even)]:bg-muted/25">
            {loading ? (
              Array.from({ length: 3 }).map((_, i) => (
                <TableRow key={`sk-${i}`} className="hover:bg-transparent">
                  <TableCell>
                    <Skeleton className="h-4 w-32" />
                  </TableCell>
                  <TableCell>
                    <Skeleton className="h-4 w-48" />
                  </TableCell>
                  <TableCell>
                    <Skeleton className="h-5 w-24" />
                  </TableCell>
                  <TableCell>
                    <Skeleton className="h-5 w-16" />
                  </TableCell>
                  <TableCell>
                    <Skeleton className="h-3 w-20" />
                  </TableCell>
                  <TableCell className="text-right">
                    <Skeleton className="ml-auto h-7 w-24" />
                  </TableCell>
                </TableRow>
              ))
            ) : users.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} className="text-sm text-muted-foreground">
                  No hay usuarios.
                </TableCell>
              </TableRow>
            ) : (
              users.map((u) => {
                const isSelf = u.id === current?.id;
                return (
                  <TableRow key={u.id}>
                    <TableCell className="font-medium">
                      {u.full_name}
                      {isSelf && (
                        <span className="ml-2 text-[11px] text-muted-foreground">
                          (tú)
                        </span>
                      )}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {u.email}
                    </TableCell>
                    <TableCell>
                      <RoleBadge role={u.role} />
                    </TableCell>
                    <TableCell>
                      <ActiveBadge active={u.is_active} />
                    </TableCell>
                    <TableCell
                      className="whitespace-nowrap text-xs text-muted-foreground"
                      title={absoluteTime(u.created_at)}
                    >
                      {relativeTime(u.created_at)}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={busyId === u.id || isSelf}
                        title={
                          isSelf
                            ? "No puedes desactivar tu propia cuenta"
                            : undefined
                        }
                        onClick={() => onToggleActive(u)}
                      >
                        {busyId === u.id ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : u.is_active ? (
                          "Desactivar"
                        ) : (
                          "Reactivar"
                        )}
                      </Button>
                    </TableCell>
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
