"use client";

import { Eye, EyeOff, Lock } from "lucide-react";
import { useId, useState } from "react";

import { cn } from "@/lib/utils";

/**
 * Campo de contraseña con **toggle mostrar/ocultar** ("ojito").
 *
 * Se usa en TODOS los campos de contraseña de la app (login, bootstrap, alta de
 * usuario y restablecimiento) para que el comportamiento sea idéntico en los
 * cuatro sitios.
 *
 * Accesibilidad: el botón no es un `<label>` ni entra en el flujo del formulario
 * (`tabIndex` normal pero `type="button"`, así no envía el formulario al pulsar
 * Enter), y anuncia su acción con `aria-label` + `aria-pressed`.
 */
export function PasswordInput({
  id,
  value,
  onChange,
  placeholder,
  disabled,
  required,
  minLength,
  autoComplete,
  className,
}: {
  id?: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  required?: boolean;
  minLength?: number;
  autoComplete?: string;
  className?: string;
}) {
  const [visible, setVisible] = useState(false);
  const fallbackId = useId();
  const inputId = id ?? fallbackId;

  return (
    <div className="relative">
      <Lock className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-meta-foreground" />
      <input
        id={inputId}
        // El tipo alterna: `text` muestra la contraseña en claro. No se guarda
        // ninguna preferencia — cada campo arranca oculto.
        type={visible ? "text" : "password"}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        disabled={disabled}
        required={required}
        minLength={minLength}
        autoComplete={autoComplete}
        // Sitio a ambos lados: candado a la izquierda, ojito a la derecha.
        className={cn("field-base pl-9 pr-10", className)}
      />
      <button
        type="button"
        onClick={() => setVisible((v) => !v)}
        disabled={disabled}
        aria-label={visible ? "Ocultar contraseña" : "Mostrar contraseña"}
        aria-pressed={visible}
        aria-controls={inputId}
        title={visible ? "Ocultar contraseña" : "Mostrar contraseña"}
        className="absolute right-1 top-1/2 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-md text-meta-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50 disabled:opacity-50"
      >
        {visible ? (
          <EyeOff className="h-4 w-4" />
        ) : (
          <Eye className="h-4 w-4" />
        )}
      </button>
    </div>
  );
}
