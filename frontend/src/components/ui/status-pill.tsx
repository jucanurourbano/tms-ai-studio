import { cn } from "@/lib/utils";

/**
 * Tono funcional de un estado. El color **significa**, no decora:
 * `success` verde, `warning` ámbar, `error` rojo, `info` azul, `neutral` gris.
 */
export type StatusTone = "success" | "warning" | "error" | "info" | "neutral";

const TONE: Record<StatusTone, { pill: string; dot: string }> = {
  success: {
    pill: "border-emerald-200 bg-emerald-50 text-emerald-700",
    dot: "bg-emerald-500",
  },
  warning: {
    pill: "border-amber-200 bg-amber-50 text-amber-800",
    dot: "bg-amber-500",
  },
  error: { pill: "border-red-200 bg-red-50 text-red-700", dot: "bg-red-500" },
  info: { pill: "border-sky-200 bg-sky-50 text-sky-700", dot: "bg-sky-500" },
  neutral: {
    pill: "border-slate-200 bg-slate-50 text-slate-600",
    dot: "bg-slate-400",
  },
};

/**
 * Pill de estado: **fondo suave + punto de color** + etiqueta.
 *
 * El punto existe para que el estado se distinga sin depender solo del tono del
 * fondo (que a esa opacidad es sutil por diseño) y para que siga siendo legible en
 * escala de grises o para alguien con daltonismo.
 */
export function StatusPill({
  tone,
  children,
  pulse = false,
  className,
  title,
}: {
  tone: StatusTone;
  children: React.ReactNode;
  /** Late cuando el estado es "en curso". */
  pulse?: boolean;
  className?: string;
  title?: string;
}) {
  const t = TONE[tone];
  return (
    <span
      title={title}
      className={cn(
        "print-color inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium whitespace-nowrap",
        t.pill,
        className,
      )}
    >
      <span
        aria-hidden
        className={cn(
          "h-1.5 w-1.5 shrink-0 rounded-full",
          t.dot,
          pulse && "animate-pulse",
        )}
      />
      {children}
    </span>
  );
}
