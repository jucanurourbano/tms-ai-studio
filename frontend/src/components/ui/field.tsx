"use client";

import { AlertCircle, CheckCircle2 } from "lucide-react";
import { useId } from "react";

import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

/**
 * Envoltura estándar de un campo: **label uniforme** + control + pista o mensaje
 * de estado. Existe para que ningún formulario invente su propia disposición y
 * para que error y éxito se muestren siempre igual: color en el borde del control
 * (vía `aria-invalid`) **y** un mensaje, nunca solo color — el color por sí solo
 * no es accesible ni dice qué hacer.
 */
export function Field({
  label,
  htmlFor,
  hint,
  error,
  success,
  required,
  className,
  children,
}: {
  label: string;
  htmlFor?: string;
  /** Ayuda permanente (formato esperado, consecuencia del campo). */
  hint?: React.ReactNode;
  error?: string | null;
  success?: string | null;
  required?: boolean;
  className?: string;
  children: React.ReactNode;
}) {
  const auto = useId();
  const id = htmlFor ?? auto;

  return (
    <div className={cn("space-y-1.5", className)}>
      <Label htmlFor={id}>
        {label}
        {required && (
          <span aria-hidden className="ml-0.5 text-destructive">
            *
          </span>
        )}
      </Label>
      {children}
      {error ? (
        <p
          role="alert"
          className="flex items-start gap-1.5 text-[11px] text-destructive"
        >
          <AlertCircle className="mt-px h-3.5 w-3.5 shrink-0" />
          {error}
        </p>
      ) : success ? (
        <p className="flex items-start gap-1.5 text-[11px] text-emerald-700">
          <CheckCircle2 className="mt-px h-3.5 w-3.5 shrink-0" />
          {success}
        </p>
      ) : hint ? (
        <p className="text-[11px] text-meta-foreground">{hint}</p>
      ) : null}
    </div>
  );
}
