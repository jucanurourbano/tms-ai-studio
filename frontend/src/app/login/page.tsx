"use client";

import { Loader2, LogIn } from "lucide-react";
import Image from "next/image";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/auth-context";

export default function LoginPage() {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
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

        {/* Tarjeta del formulario */}
        <div className="rounded-2xl bg-card p-6 shadow-xl ring-1 ring-black/5">
          <h2 className="font-heading text-lg font-semibold tracking-tight">
            Iniciar sesión
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Accede con tu correo corporativo.
          </p>

          <form onSubmit={onSubmit} className="mt-5 space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="email">Correo</Label>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
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
                onChange={(e) => setPassword(e.target.value)}
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
        </div>

        <p className="mt-6 text-center text-xs text-white/70">
          ¿Problemas para acceder? Contacta a un administrador.
        </p>
      </div>
    </div>
  );
}
