"use client";

import { useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import { authApi } from "@/lib/api/auth";
import {
  setAuthToken,
  setUnauthorizedHandler,
} from "@/lib/api/client";
import { canAccess } from "@/lib/permissions";
import type {
  AccessLevel,
  AuthUser,
  EffectiveModules,
  ModuleKey,
} from "@/lib/types/auth";

// Clave de persistencia del token. El token vive en memoria (lo adjunta el
// cliente API) y se guarda en localStorage para sobrevivir recargas.
const TOKEN_KEY = "tms:auth-token";

type AuthStatus = "loading" | "authenticated" | "unauthenticated";

interface AuthContextValue {
  status: AuthStatus;
  user: AuthUser | null;
  isAdmin: boolean;
  /** Módulos efectivos resueltos por el backend (rol + accesos adicionales). */
  modules: EffectiveModules;
  /** ¿El usuario alcanza `level` en `module`? Fuente única: `user.modules`. */
  can: (module: ModuleKey, level?: AccessLevel) => boolean;
  /** Refresca el usuario desde `/auth/me` (tras cambiarle rol o accesos). */
  refresh: () => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function readToken(): string | null {
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

function writeToken(token: string | null): void {
  try {
    if (token) window.localStorage.setItem(TOKEN_KEY, token);
    else window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* localStorage no disponible */
  }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [user, setUser] = useState<AuthUser | null>(null);

  const clearSession = useCallback(() => {
    setAuthToken(null);
    writeToken(null);
    setUser(null);
    setStatus("unauthenticated");
  }, []);

  // Handler global de 401 del cliente API: cierra sesión y manda a /login.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      clearSession();
      router.replace("/login");
    });
    return () => setUnauthorizedHandler(null);
  }, [clearSession, router]);

  // Validación inicial: si hay token guardado, se confirma contra /auth/me.
  // El estado se actualiza siempre desde callbacks asíncronos (nunca de forma
  // síncrona en el cuerpo del efecto).
  useEffect(() => {
    let cancelled = false;
    const stored = readToken();
    if (!stored) {
      Promise.resolve().then(() => {
        if (!cancelled) setStatus("unauthenticated");
      });
      return () => {
        cancelled = true;
      };
    }
    setAuthToken(stored);
    authApi
      .me()
      .then((u) => {
        if (cancelled) return;
        setUser(u);
        setStatus("authenticated");
      })
      .catch(() => {
        if (!cancelled) clearSession();
      });
    return () => {
      cancelled = true;
    };
  }, [clearSession]);

  const login = useCallback(async (email: string, password: string) => {
    const result = await authApi.login(email, password);
    setAuthToken(result.access_token);
    writeToken(result.access_token);
    setUser(result.user);
    setStatus("authenticated");
  }, []);

  const logout = useCallback(() => {
    clearSession();
    router.replace("/login");
  }, [clearSession, router]);

  // Relee el usuario (y con él sus permisos). El backend resuelve los módulos en
  // cada respuesta de /auth/me, así que un cambio de rol o de accesos se aplica
  // sin necesidad de volver a iniciar sesión: el JWT identifica, no autoriza.
  const refresh = useCallback(async () => {
    try {
      setUser(await authApi.me());
    } catch {
      /* un 401 ya lo gestiona el handler global */
    }
  }, []);

  const value = useMemo<AuthContextValue>(() => {
    const modules = user?.modules ?? {};
    return {
      status,
      user,
      isAdmin: user?.role === "admin",
      modules,
      can: (module: ModuleKey, level: AccessLevel = "read") =>
        canAccess(modules, module, level),
      refresh,
      login,
      logout,
    };
  }, [status, user, refresh, login, logout]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth debe usarse dentro de <AuthProvider>.");
  return ctx;
}
