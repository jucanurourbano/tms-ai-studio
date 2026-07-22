"use client";

import { Loader2 } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import { AppShell } from "@/components/shell/app-shell";
import { useAuth } from "@/lib/auth/auth-context";

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
 * - Las rutas autenticadas se envuelven en ``AppShell`` (sidebar); ``/login`` se
 *   muestra sin shell.
 */
export function AppGate({ children }: { children: React.ReactNode }) {
  const { status } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const isLogin = pathname === LOGIN_PATH;

  useEffect(() => {
    if (status === "loading") return;
    if (status === "unauthenticated" && !isLogin) router.replace(LOGIN_PATH);
    if (status === "authenticated" && isLogin) router.replace("/");
  }, [status, isLogin, router]);

  if (isLogin) {
    // Evita el parpadeo del login mientras se redirige a un usuario autenticado.
    if (status === "authenticated") return <FullScreenLoader />;
    return <>{children}</>;
  }

  if (status !== "authenticated") return <FullScreenLoader />;
  return <AppShell>{children}</AppShell>;
}
