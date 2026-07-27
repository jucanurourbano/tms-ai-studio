"use client";

import { Loader2, LogIn, Mail, ShieldPlus, User } from "lucide-react";
import Image from "next/image";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { IconInput } from "@/components/ui/icon-input";
import { PasswordInput } from "@/components/ui/password-input";
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
        <div className="gradient-border rounded-2xl bg-card p-6 shadow-xl ring-1 ring-black/5">
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

        <Field label="Correo" htmlFor="email" required>
          <IconInput
            id="email"
            icon={Mail}
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => onEmail(e.target.value)}
            placeholder="nombre@urbano.com.pe"
            disabled={submitting}
            invalid={!!error}
          />
        </Field>

        <Field label="Contraseña" htmlFor="password" required>
          <PasswordInput
            id="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={onPassword}
            placeholder="••••••••"
            disabled={submitting}
          />
        </Field>

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
        <Field label="Nombre completo" htmlFor="fullName" required>
          <IconInput
            id="fullName"
            icon={User}
            autoComplete="name"
            required
            value={fullName}
            onChange={(e) => onFullName(e.target.value)}
            placeholder="Nombre Apellido"
            disabled={submitting}
          />
        </Field>

        <Field label="Correo" htmlFor="bEmail" required>
          <IconInput
            id="bEmail"
            icon={Mail}
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => onEmail(e.target.value)}
            placeholder="nombre@urbano.com.pe"
            disabled={submitting}
          />
        </Field>

        <Field
          label="Contraseña"
          htmlFor="bPassword"
          required
          hint="Mínimo 8 caracteres."
        >
          <PasswordInput
            id="bPassword"
            autoComplete="new-password"
            required
            minLength={8}
            value={password}
            onChange={onPassword}
            placeholder="Mínimo 8 caracteres"
            disabled={submitting}
          />
        </Field>

        <Field
          label="Confirmar contraseña"
          htmlFor="bConfirm"
          required
          // Estado en vivo: se avisa en cuanto ambas tienen contenido, sin
          // esperar al submit.
          error={
            confirm.length > 0 && confirm !== password
              ? "Las contraseñas no coinciden."
              : null
          }
          success={
            confirm.length > 0 && confirm === password
              ? "Las contraseñas coinciden."
              : null
          }
        >
          <PasswordInput
            id="bConfirm"
            autoComplete="new-password"
            required
            value={confirm}
            onChange={onConfirm}
            placeholder="Repite la contraseña"
            disabled={submitting}
          />
        </Field>

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
