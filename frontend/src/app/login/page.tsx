"use client";

import { Loader2, LogIn, ShieldPlus } from "lucide-react";
import Image from "next/image";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { authApi } from "@/lib/api/auth";
import { ApiError } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/auth-context";

type Mode = "checking" | "login" | "bootstrap";

export default function LoginPage() {
  const { login } = useAuth();
  const [mode, setMode] = useState<Mode>("checking");

  // Campos compartidos (login) + específicos del bootstrap.
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [confirm, setConfirm] = useState("");

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // ¿La plataforma aún no tiene usuarios? Entonces ofrecemos crear el primer
  // administrador; en caso contrario, login normal. (setState solo en callbacks
  // async: nunca síncrono dentro del efecto.)
  useEffect(() => {
    let cancelled = false;
    authApi
      .bootstrapStatus()
      .then((s) => {
        if (!cancelled) setMode(s.needs_bootstrap ? "bootstrap" : "login");
      })
      .catch(() => {
        // Si el chequeo falla (p. ej. backend caído), caemos al login normal;
        // el propio login mostrará el error de conexión al intentar.
        if (!cancelled) setMode("login");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function onLogin(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
      // El AppGate redirige al dashboard cuando la sesión queda activa.
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "No se pudo iniciar sesión. Inténtalo de nuevo.",
      );
      setSubmitting(false);
    }
  }

  async function onBootstrap(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (password.length < 8) {
      setError("La contraseña debe tener al menos 8 caracteres.");
      return;
    }
    if (password !== confirm) {
      setError("Las contraseñas no coinciden.");
      return;
    }
    setSubmitting(true);
    try {
      await authApi.register({
        email,
        full_name: fullName,
        password,
        role: "admin",
      });
      // Cuenta creada: pasamos al login normal (nunca más registro público).
      setPassword("");
      setConfirm("");
      setFullName("");
      setNotice("Cuenta de administrador creada. Inicia sesión para continuar.");
      setMode("login");
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "No se pudo crear la cuenta. Inténtalo de nuevo.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="hero-ai flex min-h-screen items-center justify-center p-4">
      <div className="w-full max-w-sm">
        {/* Marca Urbano */}
        <div className="mb-6 flex flex-col items-center text-center text-white">
          <Image
            src="/logo-urbano.png"
            alt="Urbano"
            width={56}
            height={56}
            priority
            className="rounded-xl ring-1 ring-white/30"
          />
          <h1 className="mt-4 font-heading text-2xl font-semibold tracking-tight">
            TMS AI Studio
          </h1>
          <p className="mt-1 text-sm text-white/80">ISDF · Urbano TI</p>
        </div>

        {/* Tarjeta */}
        <div className="rounded-2xl bg-card p-6 shadow-xl ring-1 ring-black/5">
          {mode === "checking" && (
            <div className="flex items-center justify-center py-10">
              <Loader2 className="h-6 w-6 animate-spin text-primary" />
              <span className="sr-only">Comprobando…</span>
            </div>
          )}

          {mode === "bootstrap" && (
            <BootstrapForm
              fullName={fullName}
              email={email}
              password={password}
              confirm={confirm}
              submitting={submitting}
              error={error}
              onFullName={setFullName}
              onEmail={setEmail}
              onPassword={setPassword}
              onConfirm={setConfirm}
              onSubmit={onBootstrap}
            />
          )}

          {mode === "login" && (
            <LoginForm
              email={email}
              password={password}
              submitting={submitting}
              error={error}
              notice={notice}
              onEmail={setEmail}
              onPassword={setPassword}
              onSubmit={onLogin}
            />
          )}
        </div>

        <p className="mt-6 text-center text-xs text-white/70">
          {mode === "bootstrap"
            ? "Esta es la configuración inicial de la plataforma."
            : "¿Problemas para acceder? Contacta a un administrador."}
        </p>
      </div>
    </div>
  );
}

function LoginForm({
  email,
  password,
  submitting,
  error,
  notice,
  onEmail,
  onPassword,
  onSubmit,
}: {
  email: string;
  password: string;
  submitting: boolean;
  error: string | null;
  notice: string | null;
  onEmail: (v: string) => void;
  onPassword: (v: string) => void;
  onSubmit: (e: React.FormEvent) => void;
}) {
  return (
    <>
      <h2 className="font-heading text-lg font-semibold tracking-tight">
        Iniciar sesión
      </h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Accede con tu correo corporativo.
      </p>

      <form onSubmit={onSubmit} className="mt-5 space-y-4">
        {notice && (
          <div className="rounded-md border border-emerald-300 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
            {notice}
          </div>
        )}

        <div className="space-y-1.5">
          <Label htmlFor="email">Correo</Label>
          <Input
            id="email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => onEmail(e.target.value)}
            placeholder="nombre@urbano.com.pe"
            disabled={submitting}
          />
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="password">Contraseña</Label>
          <Input
            id="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => onPassword(e.target.value)}
            placeholder="••••••••"
            disabled={submitting}
          />
        </div>

        {error && (
          <div
            role="alert"
            className="rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700"
          >
            {error}
          </div>
        )}

        <Button
          type="submit"
          size="lg"
          className="w-full gap-2"
          disabled={submitting || !email || !password}
        >
          {submitting ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <LogIn className="h-4 w-4" />
          )}
          {submitting ? "Ingresando…" : "Ingresar"}
        </Button>
      </form>
    </>
  );
}

function BootstrapForm({
  fullName,
  email,
  password,
  confirm,
  submitting,
  error,
  onFullName,
  onEmail,
  onPassword,
  onConfirm,
  onSubmit,
}: {
  fullName: string;
  email: string;
  password: string;
  confirm: string;
  submitting: boolean;
  error: string | null;
  onFullName: (v: string) => void;
  onEmail: (v: string) => void;
  onPassword: (v: string) => void;
  onConfirm: (v: string) => void;
  onSubmit: (e: React.FormEvent) => void;
}) {
  return (
    <>
      <h2 className="font-heading text-lg font-semibold tracking-tight">
        Crear cuenta de administrador
      </h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Aún no hay usuarios. Esta primera cuenta será administradora.
      </p>

      <form onSubmit={onSubmit} className="mt-5 space-y-4">
        <div className="space-y-1.5">
          <Label htmlFor="fullName">Nombre completo</Label>
          <Input
            id="fullName"
            autoComplete="name"
            required
            value={fullName}
            onChange={(e) => onFullName(e.target.value)}
            placeholder="Nombre Apellido"
            disabled={submitting}
          />
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="bEmail">Correo</Label>
          <Input
            id="bEmail"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => onEmail(e.target.value)}
            placeholder="nombre@urbano.com.pe"
            disabled={submitting}
          />
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="bPassword">Contraseña</Label>
          <Input
            id="bPassword"
            type="password"
            autoComplete="new-password"
            required
            minLength={8}
            value={password}
            onChange={(e) => onPassword(e.target.value)}
            placeholder="Mínimo 8 caracteres"
            disabled={submitting}
          />
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="bConfirm">Confirmar contraseña</Label>
          <Input
            id="bConfirm"
            type="password"
            autoComplete="new-password"
            required
            value={confirm}
            onChange={(e) => onConfirm(e.target.value)}
            placeholder="Repite la contraseña"
            disabled={submitting}
          />
        </div>

        {error && (
          <div
            role="alert"
            className="rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700"
          >
            {error}
          </div>
        )}

        <Button
          type="submit"
          size="lg"
          className="w-full gap-2"
          disabled={
            submitting || !fullName || !email || !password || !confirm
          }
        >
          {submitting ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <ShieldPlus className="h-4 w-4" />
          )}
          {submitting ? "Creando…" : "Crear administrador"}
        </Button>
      </form>
    </>
  );
}
