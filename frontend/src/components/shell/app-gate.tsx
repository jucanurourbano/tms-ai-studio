"use client";

import { Loader2 } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { toast } from "sonner";

import { AppShell } from "@/components/shell/app-shell";
import { useAuth } from "@/lib/auth/auth-context";
import { MODULE_LABELS } from "@/lib/permissions";
import { ruleFor } from "@/lib/route-permissions";

const LOGIN_PATH = "/login";

function FullScreenLoader() {
  return (
    <div className="flex h-screen items-center justify-center bg-background">
      <Loader2 className="h-6 w-6 animate-spin text-primary" />
      <span className="sr-only">Cargando…</span>
    </div>
  );
}

/**
 * Guarda de rutas y decisión de layout:
 * - Sin sesión, cualquier ruta protegida redirige a ``/login``.
 * - Con sesión, ``/login`` redirige al dashboard.
 * - Con sesión pero SIN permiso para la ruta (acceso por URL directa), redirige
 *   al dashboard con un aviso que nombra el módulo. Es usabilidad, no
 *   seguridad: el backend responde 403 igualmente (``require_module``).
 * - Las rutas autenticadas se envuelven en ``AppShell`` (sidebar); ``/login`` se
 *   muestra sin shell.
 */
export function AppGate({ children }: { children: React.ReactNode }) {
  const { status, can } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const isLogin = pathname === LOGIN_PATH;

  const rule = isLogin ? null : ruleFor(pathname);
  const allowed = !rule || can(rule.module, rule.level);

  useEffect(() => {
    if (status === "loading") return;
    if (status === "unauthenticated" && !isLogin) router.replace(LOGIN_PATH);
    if (status === "authenticated" && isLogin) router.replace("/");
  }, [status, isLogin, router]);

  useEffect(() => {
    if (status !== "authenticated" || !rule || allowed) return;
    const modulo = MODULE_LABELS[rule.module];
    toast.error(
      rule.level === "full"
        ? `No tienes permiso de edición en ${modulo}.`
        : `No tienes acceso a ${modulo}.`,
      { description: "Pide a un administrador que te asigne este módulo." },
    );
    router.replace("/");
  }, [status, rule, allowed, router]);

  if (isLogin) {
    // Evita el parpadeo del login mientras se redirige a un usuario autenticado.
    if (status === "authenticated") return <FullScreenLoader />;
    return <>{children}</>;
  }

  if (status !== "authenticated") return <FullScreenLoader />;
  // Sin permiso: no se monta la página (evita que dispare peticiones que la API
  // rechazaría con 403) mientras el efecto redirige.
  if (!allowed) return <FullScreenLoader />;
  return <AppShell>{children}</AppShell>;
}
