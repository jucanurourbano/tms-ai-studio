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
import type { AuthUser } from "@/lib/types/auth";

// Clave de persistencia del token. El token vive en memoria (lo adjunta el
// cliente API) y se guarda en localStorage para sobrevivir recargas.
const TOKEN_KEY = "tms:auth-token";

type AuthStatus = "loading" | "authenticated" | "unauthenticated";

interface AuthContextValue {
  status: AuthStatus;
  user: AuthUser | null;
  isAdmin: boolean;
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

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user,
      isAdmin: user?.role === "admin",
      login,
      logout,
    }),
    [status, user, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth debe usarse dentro de <AuthProvider>.");
  return ctx;
}
