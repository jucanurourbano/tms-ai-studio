import { FileSearch, History, Sparkles } from "lucide-react";
import Link from "next/link";

/**
 * Hero del dashboard con identidad de producto IA: degradado violeta profundo y
 * motivo sutil de constelación (clase `.hero-ai`, CSS puro), título + tagline y
 * dos CTAs (nuevo análisis EF / ver historial).
 */
export function DashboardHero() {
  return (
    <section className="hero-ai relative mb-6 overflow-hidden rounded-2xl px-6 py-10 text-white shadow-sm sm:px-10 sm:py-12">
      <div className="relative max-w-2xl">
        <div className="inline-flex items-center gap-1.5 rounded-full bg-white/15 px-3 py-1 text-[11px] font-semibold uppercase tracking-widest text-white/90 ring-1 ring-white/25">
          <Sparkles className="h-3.5 w-3.5" />
          ISDF · Urbano TI
        </div>

        <h1 className="mt-4 font-heading text-3xl font-semibold tracking-tight sm:text-4xl">
          TMS AI Studio
        </h1>
        <p className="mt-3 max-w-xl text-sm leading-relaxed text-white/85 sm:text-base">
          Agentes de IA que asisten el ciclo de vida del desarrollo de software
          —del entendimiento del negocio a la planificación ágil— con
          trazabilidad de extremo a extremo.
        </p>

        <div className="mt-6 flex flex-wrap gap-3">
          <Link
            href="/agents/ef/new"
            className="inline-flex items-center gap-2 rounded-lg bg-white px-4 py-2 text-sm font-semibold text-violet-800 shadow-sm transition-all hover:bg-white/90 hover:shadow focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70 focus-visible:ring-offset-2 focus-visible:ring-offset-violet-800"
          >
            <FileSearch className="h-4 w-4" />
            Nuevo análisis EF
          </Link>
          <Link
            href="/agents/ef/jobs"
            className="inline-flex items-center gap-2 rounded-lg border border-white/40 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-white/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70 focus-visible:ring-offset-2 focus-visible:ring-offset-violet-800"
          >
            <History className="h-4 w-4" />
            Ver historial
          </Link>
        </div>
      </div>
    </section>
  );
}
