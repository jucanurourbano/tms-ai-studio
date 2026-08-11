// Acento de color por módulo del ISDF.
//
// El violeta de marca sigue mandando en la navegación y en las acciones primarias;
// estos acentos solo identifican al módulo (icono de la sidebar, cabecera de la
// vista y badge), para que el ojo distinga "esto es Scrum" de "esto es
// Arquitectura" sin leer. Son tonos SUAVES: fondo al 10-15% de opacidad con el
// icono y el texto en el tono pleno — nunca bloques de color saturado.
//
// Se usan clases estáticas (no plantillas tipo `bg-${color}-50`) porque Tailwind
// necesita ver la clase literal para incluirla en el CSS final.

import type { ModuleKey } from "@/lib/types/auth";

export interface ModuleAccent {
  /** Fondo tenue + texto pleno, para el contenedor del icono y los badges. */
  soft: string;
  /** Solo el color del texto/icono, para acentos sobre fondo neutro. */
  text: string;
  /** Anillo hairline a juego. */
  ring: string;
  /** Texto en el tono al hacer hover en la tarjeta (clase literal: Tailwind
   *  necesita verla escrita para incluirla en el CSS). */
  groupHoverText: string;
  /** Degradado suave para el contenedor del icono de la tarjeta del hub. */
  iconGradient: string;
  /** Anillo del tono al pasar por encima de la tarjeta. */
  hoverRing: string;
}

const VIOLETA: ModuleAccent = {
  soft: "bg-violet-100 text-violet-700",
  text: "text-violet-600",
  ring: "ring-violet-200",
  groupHoverText: "group-hover:text-violet-600",
  iconGradient: "bg-gradient-to-br from-violet-100 to-violet-50 text-violet-700",
  hoverRing: "hover:ring-violet-300",
};

/**
 * Un tono por módulo, elegido para que sean distinguibles entre sí y coherentes
 * con la marca: la fase de especificar se queda en el violeta de Urbano, y el
 * resto se reparte por el círculo sin salirse de los tonos apagados.
 */
export const MODULE_ACCENT: Record<ModuleKey, ModuleAccent> = {
  // ESPECIFICAR — violeta de marca: es la puerta de entrada del ISDF.
  ef: VIOLETA,
  // DISEÑAR — teal para Arquitectura, cian para el modelo de datos.
  arquitectura: {
    soft: "bg-teal-100 text-teal-700",
    text: "text-teal-600",
    ring: "ring-teal-200",
    groupHoverText: "group-hover:text-teal-600",
    iconGradient: "bg-gradient-to-br from-teal-100 to-teal-50 text-teal-700",
    hoverRing: "hover:ring-teal-300",
  },
  bd: {
    soft: "bg-cyan-100 text-cyan-700",
    text: "text-cyan-600",
    ring: "ring-cyan-200",
    groupHoverText: "group-hover:text-cyan-600",
    iconGradient: "bg-gradient-to-br from-cyan-100 to-cyan-50 text-cyan-700",
    hoverRing: "hover:ring-cyan-300",
  },
  // CONSTRUIR — la familia índigo/azul, que se lee como "una misma fase".
  api: {
    soft: "bg-indigo-100 text-indigo-700",
    text: "text-indigo-600",
    ring: "ring-indigo-200",
    groupHoverText: "group-hover:text-indigo-600",
    iconGradient: "bg-gradient-to-br from-indigo-100 to-indigo-50 text-indigo-700",
    hoverRing: "hover:ring-indigo-300",
  },
  backend: {
    soft: "bg-sky-100 text-sky-700",
    text: "text-sky-600",
    ring: "ring-sky-200",
    groupHoverText: "group-hover:text-sky-600",
    iconGradient: "bg-gradient-to-br from-sky-100 to-sky-50 text-sky-700",
    hoverRing: "hover:ring-sky-300",
  },
  frontend: {
    soft: "bg-blue-100 text-blue-700",
    text: "text-blue-600",
    ring: "ring-blue-200",
    groupHoverText: "group-hover:text-blue-600",
    iconGradient: "bg-gradient-to-br from-blue-100 to-blue-50 text-blue-700",
    hoverRing: "hover:ring-blue-300",
  },
  // VERIFICAR — ámbar: el color con el que ya se marcan las advertencias.
  qa: {
    soft: "bg-amber-100 text-amber-700",
    text: "text-amber-600",
    ring: "ring-amber-200",
    groupHoverText: "group-hover:text-amber-600",
    iconGradient: "bg-gradient-to-br from-amber-100 to-amber-50 text-amber-700",
    hoverRing: "hover:ring-amber-300",
  },
  // GESTIONAR — azul para Scrum, esmeralda para DevOps (entrega).
  scrum: {
    soft: "bg-blue-100 text-blue-700",
    text: "text-blue-600",
    ring: "ring-blue-200",
    groupHoverText: "group-hover:text-blue-600",
    iconGradient: "bg-gradient-to-br from-blue-100 to-blue-50 text-blue-700",
    hoverRing: "hover:ring-blue-300",
  },
  devops: {
    soft: "bg-emerald-100 text-emerald-700",
    text: "text-emerald-600",
    ring: "ring-emerald-200",
    groupHoverText: "group-hover:text-emerald-600",
    iconGradient: "bg-gradient-to-br from-emerald-100 to-emerald-50 text-emerald-700",
    hoverRing: "hover:ring-emerald-300",
  },
  // Inventario: piedra. Neutro cálido, distinto del gris de Configuración, para
  // que se lea como "esto no es una fase del ISDF, es la memoria de lo que hay".
  inventario: {
    soft: "bg-stone-100 text-stone-700",
    text: "text-stone-600",
    ring: "ring-stone-200",
    groupHoverText: "group-hover:text-stone-600",
    iconGradient: "bg-gradient-to-br from-stone-100 to-stone-50 text-stone-700",
    hoverRing: "hover:ring-stone-300",
  },
  // Configuración: neutro a propósito, no es una fase del ISDF.
  config: {
    soft: "bg-slate-100 text-slate-700",
    text: "text-slate-600",
    ring: "ring-slate-200",
    groupHoverText: "group-hover:text-slate-600",
    iconGradient: "bg-gradient-to-br from-slate-100 to-slate-50 text-slate-700",
    hoverRing: "hover:ring-slate-300",
  },
};

export function accentOf(module: ModuleKey | undefined): ModuleAccent {
  return module ? MODULE_ACCENT[module] : VIOLETA;
}
