"use client";

import { Loader2, ShieldAlert, UserPlus, Users } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { UserActionsMenu } from "@/components/configuracion/user-actions-menu";
import { PageContainer } from "@/components/shell/page-container";
import { PageHeader } from "@/components/shell/page-header";
import { DataTable, type DataColumn } from "@/components/ui/data-table";
import { NativeSelect } from "@/components/ui/native-select";
import { SearchInput } from "@/components/ui/search-input";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PasswordInput } from "@/components/ui/password-input";
import { authApi } from "@/lib/api/auth";
import { ApiError } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/auth-context";
import { absoluteTime, relativeTime } from "@/lib/format";
import { ALL_ROLES, ROLE_LABELS, SPECIALTY_LABELS } from "@/lib/permissions";
import type { AuthUser, RolesCatalog, UserRole } from "@/lib/types/auth";

type EstadoFiltro = "todos" | "activos" | "inactivos";

function RoleBadge({ role }: { role: UserRole }) {
  // El admin se distingue en violeta (permisos totales); el resto de roles
  // funcionales comparten un badge neutro con su etiqueta.
  return (
    <Badge
      variant="outline"
      className={
        role === "admin"
          ? "border-violet-300 bg-violet-50 text-violet-700"
          : "text-muted-foreground"
      }
    >
      {ROLE_LABELS[role] ?? role}
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
  // El PANEL se abre con acceso al módulo `config` (rol o acceso adicional);
  // cambiar roles y accesos exige rol admin estricto — el backend lo impone y
  // aquí se refleja deshabilitando los controles (ver `require_admin_role`).
  const { user: current, isAdmin, can, refresh } = useAuth();
  const puedeVerPanel = can("config");
  const [users, setUsers] = useState<AuthUser[]>([]);
  const [catalog, setCatalog] = useState<RolesCatalog | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Formulario de alta.
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<UserRole>("analista");
  const [submitting, setSubmitting] = useState(false);

  // Filtros del listado (client-side sobre la página cargada, como el historial).
  const [query, setQuery] = useState("");
  const [roleFilter, setRoleFilter] = useState<UserRole | "todos">("todos");
  const [statusFilter, setStatusFilter] = useState<EstadoFiltro>("todos");

  const filtrando =
    query.trim() !== "" || roleFilter !== "todos" || statusFilter !== "todos";

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return users.filter((u) => {
      if (q && !`${u.full_name} ${u.email}`.toLowerCase().includes(q)) {
        return false;
      }
      if (roleFilter !== "todos" && u.role !== roleFilter) return false;
      if (statusFilter === "activos" && !u.is_active) return false;
      if (statusFilter === "inactivos" && u.is_active) return false;
      return true;
    });
  }, [users, query, roleFilter, statusFilter]);

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
    if (puedeVerPanel) fetchUsers();
  }, [puedeVerPanel, fetchUsers]);

  // Catálogo de roles/módulos: la matriz la define el backend, no el cliente.
  useEffect(() => {
    if (!puedeVerPanel) return;
    let cancelled = false;
    authApi
      .roles()
      .then((c) => {
        if (!cancelled) setCatalog(c);
      })
      .catch(() => {
        /* el editor funciona sin el contexto "por rol" */
      });
    return () => {
      cancelled = true;
    };
  }, [puedeVerPanel]);

  async function onRegister(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      await authApi.register({ email, full_name: fullName, password, role });
      toast.success("Usuario registrado");
      setFullName("");
      setEmail("");
      setPassword("");
      setRole("analista");
      fetchUsers();
    } catch (err) {
      toast.error(
        err instanceof ApiError ? err.message : "No se pudo registrar el usuario.",
      );
    } finally {
      setSubmitting(false);
    }
  }



  if (!puedeVerPanel) {
    return (
      <PageContainer variant="notice">
        <div className="flex items-start gap-3 rounded-xl border border-amber-300 bg-amber-50 p-4 text-amber-800">
          <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0" />
          <div>
            <h1 className="font-heading text-base font-semibold">
              Acceso restringido
            </h1>
            <p className="mt-1 text-sm">
              No tienes acceso al módulo de Configuración. Pide a un
              administrador que te lo asigne.
            </p>
          </div>
        </div>
      </PageContainer>
    );
  }

  const columnas: DataColumn<AuthUser>[] = [
    {
      key: "full_name",
      label: "Nombre",
      cardRole: "title",
      render: (u) => (
        <span className="font-medium">
          {u.full_name}
          {u.id === current?.id && (
            <span className="ml-2 text-[11px] font-normal text-meta-foreground">
              (tú)
            </span>
          )}
        </span>
      ),
    },
    {
      key: "email",
      label: "Correo",
      cardRole: "meta",
      render: (u) => <span className="text-muted-foreground">{u.email}</span>,
    },
    {
      key: "role",
      label: "Rol",
      width: "w-36",
      cardRole: "badge",
      render: (u) => <RoleBadge role={u.role} />,
    },
    {
      key: "is_active",
      label: "Estado",
      width: "w-28",
      cardRole: "badge",
      render: (u) => <ActiveBadge active={u.is_active} />,
    },
    {
      key: "specialty",
      label: "Especialidad",
      width: "w-32",
      render: (u) => (
        <span className="text-xs text-meta-foreground">
          {u.specialty ? SPECIALTY_LABELS[u.specialty] : "—"}
        </span>
      ),
    },
    {
      key: "created_at",
      label: "Registrado",
      width: "w-28",
      nowrap: true,
      render: (u) => (
        <span
          className="text-xs text-meta-foreground"
          title={absoluteTime(u.created_at)}
        >
          {relativeTime(u.created_at)}
        </span>
      ),
    },
    {
      key: "acciones",
      label: "Acciones",
      width: "w-20",
      numeric: true,
      cardRole: "actions",
      render: (u) => (
        <UserActionsMenu
          user={u}
          catalog={catalog}
          isAdmin={isAdmin}
          isSelf={u.id === current?.id}
          onChanged={() => {
            fetchUsers();
            if (u.id === current?.id) void refresh();
          }}
        />
      ),
    },
  ];

  return (
    <PageContainer className="animate-rise">
      <PageHeader
        eyebrow="Configuración"
        title="Usuarios"
        description="Administra el acceso a TMS AI Studio: registra usuarios, asigna su rol funcional y concede accesos adicionales por módulo."
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
              <PasswordInput
                id="newPassword"
                required
                minLength={8}
                value={password}
                onChange={setPassword}
                autoComplete="new-password"
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
                {ALL_ROLES.map((r) => (
                  <option key={r} value={r}>
                    {ROLE_LABELS[r]}
                  </option>
                ))}
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
        <div className="mb-4 rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      <DataTable
        columns={columnas}
        rows={filtered}
        rowKey={(u) => u.id}
        loading={loading}
        zebra
        empty={
          filtrando
            ? "Ningún usuario coincide con los filtros."
            : "No hay usuarios."
        }
        toolbar={
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <SearchInput
              value={query}
              onChange={setQuery}
              placeholder="Buscar por nombre o correo…"
              aria-label="Buscar usuarios"
              className="sm:max-w-xs"
            />
            <div className="flex gap-2">
              <NativeSelect
                value={roleFilter}
                onChange={(e) =>
                  setRoleFilter(e.target.value as UserRole | "todos")
                }
                aria-label="Filtrar por rol"
                className="text-xs sm:w-40"
              >
                <option value="todos">Todos los roles</option>
                {ALL_ROLES.map((r) => (
                  <option key={r} value={r}>
                    {ROLE_LABELS[r]}
                  </option>
                ))}
              </NativeSelect>
              <NativeSelect
                value={statusFilter}
                onChange={(e) =>
                  setStatusFilter(e.target.value as EstadoFiltro)
                }
                aria-label="Filtrar por estado"
                className="text-xs sm:w-44"
              >
                <option value="todos">Activos e inactivos</option>
                <option value="activos">Solo activos</option>
                <option value="inactivos">Solo inactivos</option>
              </NativeSelect>
            </div>
            {/* Contador: refleja el filtro y, cuando filtra, también el total. */}
            <span className="inline-flex items-center gap-1.5 text-xs text-meta-foreground sm:ml-auto">
              <Users className="h-3.5 w-3.5" />
              {filtrando
                ? `${filtered.length} de ${users.length} usuarios`
                : `${users.length} ${users.length === 1 ? "usuario" : "usuarios"}`}
            </span>
          </div>
        }
      />
    </PageContainer>
  );
}
