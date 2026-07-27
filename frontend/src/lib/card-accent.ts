// Micro-identidad visual de cada SECCIÓN del hub.
//
// El acento de módulo (`module-accent.ts`) dice "esto es Scrum"; este dice "esto
// es Requisitos". Son complementarios: el módulo manda en la navegación de la
// app, y dentro de un artefacto cada sección se distingue de sus hermanas para
// que el ojo aprenda el sitio de cada cosa sin leer los títulos.
//
// El acento se aplica en tres capas, siempre sutiles: la barra superior de la
// tarjeta, el degradado del contenedor del icono y el glow del hover; la cifra
// grande toma el mismo tono. Todas las clases son LITERALES porque Tailwind
// necesita verlas escritas para incluirlas en el CSS final.

export type SectionTone =
  | "violet"
  | "rose"
  | "indigo"
  | "teal"
  | "amber"
  | "blue"
  | "cyan"
  | "sky"
  | "emerald"
  | "danger";

export interface ToneStyles {
  /** Barra de acento del canto superior de la tarjeta. */
  bar: string;
  /** Degradado del contenedor del icono. */
  icon: string;
  /** Color de la cifra protagonista. */
  number: string;
  /** Anillo del tono al pasar por encima. */
  hoverRing: string;
  /** Glow tenue del tono al pasar por encima (sombra proyectada, no neón). */
  hoverGlow: string;
  /** Color del patrón decorativo de fondo. */
  pattern: string;
  /** Fondo tenue + texto pleno (icono del panel y pill activa). */
  soft: string;
  /** Anillo hairline a juego. */
  ring: string;
}

export const SECTION_TONE: Record<SectionTone, ToneStyles> = {
  violet: {
    bar: "bg-violet-500",
    icon: "bg-gradient-to-br from-violet-100 to-violet-50 text-violet-600",
    number: "text-violet-700",
    hoverRing: "hover:ring-violet-300",
    hoverGlow: "hover:shadow-violet-500/15",
    pattern: "text-violet-600",
    soft: "bg-violet-100 text-violet-700",
    ring: "ring-violet-200",
  },
  rose: {
    bar: "bg-rose-500",
    icon: "bg-gradient-to-br from-rose-100 to-rose-50 text-rose-600",
    number: "text-rose-700",
    hoverRing: "hover:ring-rose-300",
    hoverGlow: "hover:shadow-rose-500/15",
    pattern: "text-rose-600",
    soft: "bg-rose-100 text-rose-700",
    ring: "ring-rose-200",
  },
  indigo: {
    bar: "bg-indigo-500",
    icon: "bg-gradient-to-br from-indigo-100 to-indigo-50 text-indigo-600",
    number: "text-indigo-700",
    hoverRing: "hover:ring-indigo-300",
    hoverGlow: "hover:shadow-indigo-500/15",
    pattern: "text-indigo-600",
    soft: "bg-indigo-100 text-indigo-700",
    ring: "ring-indigo-200",
  },
  teal: {
    bar: "bg-teal-500",
    icon: "bg-gradient-to-br from-teal-100 to-teal-50 text-teal-600",
    number: "text-teal-700",
    hoverRing: "hover:ring-teal-300",
    hoverGlow: "hover:shadow-teal-500/15",
    pattern: "text-teal-600",
    soft: "bg-teal-100 text-teal-700",
    ring: "ring-teal-200",
  },
  amber: {
    bar: "bg-amber-500",
    icon: "bg-gradient-to-br from-amber-100 to-amber-50 text-amber-600",
    number: "text-amber-700",
    hoverRing: "hover:ring-amber-300",
    hoverGlow: "hover:shadow-amber-500/15",
    pattern: "text-amber-600",
    soft: "bg-amber-100 text-amber-700",
    ring: "ring-amber-200",
  },
  blue: {
    bar: "bg-blue-500",
    icon: "bg-gradient-to-br from-blue-100 to-blue-50 text-blue-600",
    number: "text-blue-700",
    hoverRing: "hover:ring-blue-300",
    hoverGlow: "hover:shadow-blue-500/15",
    pattern: "text-blue-600",
    soft: "bg-blue-100 text-blue-700",
    ring: "ring-blue-200",
  },
  cyan: {
    bar: "bg-cyan-500",
    icon: "bg-gradient-to-br from-cyan-100 to-cyan-50 text-cyan-600",
    number: "text-cyan-700",
    hoverRing: "hover:ring-cyan-300",
    hoverGlow: "hover:shadow-cyan-500/15",
    pattern: "text-cyan-600",
    soft: "bg-cyan-100 text-cyan-700",
    ring: "ring-cyan-200",
  },
  sky: {
    bar: "bg-sky-500",
    icon: "bg-gradient-to-br from-sky-100 to-sky-50 text-sky-600",
    number: "text-sky-700",
    hoverRing: "hover:ring-sky-300",
    hoverGlow: "hover:shadow-sky-500/15",
    pattern: "text-sky-600",
    soft: "bg-sky-100 text-sky-700",
    ring: "ring-sky-200",
  },
  emerald: {
    bar: "bg-emerald-500",
    icon: "bg-gradient-to-br from-emerald-100 to-emerald-50 text-emerald-600",
    number: "text-emerald-700",
    hoverRing: "hover:ring-emerald-300",
    hoverGlow: "hover:shadow-emerald-500/15",
    pattern: "text-emerald-600",
    soft: "bg-emerald-100 text-emerald-700",
    ring: "ring-emerald-200",
  },
  // Urgencia: sustituye al tono propio de la sección cuando algo reclama acción.
  danger: {
    bar: "bg-red-600",
    icon: "bg-gradient-to-br from-red-100 to-red-50 text-red-600",
    number: "text-red-700",
    hoverRing: "hover:ring-red-400",
    hoverGlow: "hover:shadow-red-500/20",
    pattern: "text-red-600",
    soft: "bg-red-100 text-red-700",
    ring: "ring-red-200",
  },
};

/** Patrón decorativo del fondo, elegido por la NATURALEZA de la sección. */
export type SectionPattern = "dots" | "lines" | "waves";

const PATTERN_CLASS: Record<SectionPattern, string> = {
  dots: "hub-pattern-dots",
  lines: "hub-pattern-lines",
  waves: "hub-pattern-waves",
};

export function toneOf(tone: SectionTone | undefined): ToneStyles {
  return SECTION_TONE[tone ?? "violet"];
}

export function patternClassOf(pattern: SectionPattern | undefined): string | null {
  return pattern ? PATTERN_CLASS[pattern] : null;
}
