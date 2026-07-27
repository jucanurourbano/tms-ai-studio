"use client";

// DOCUMENTO LINEAL IMPRIMIBLE — el PDF no usa paneles.
//
// En pantalla el artefacto se explora por tarjetas y panel lateral; al exportar,
// el informe vuelve a ser lo que un informe debe ser: portada, índice y todos los
// capítulos seguidos, sin nada plegado. Se consigue reutilizando el MISMO
// `render` de cada sección con `forPrint: true` — una sola definición del
// contenido, dos presentaciones.
//
// Solo se construye cuando `active` (es decir, cuando `usePrintExpand` detecta
// que se va a imprimir): montar todos los capítulos en cada render de la página
// sería pagar el coste del documento completo para no mostrarlo nunca.

import type { HubSection } from "@/components/artifact/artifact-panel";
import { GroupLabel } from "@/components/artifact/primitives";

export function ArtifactPrintDoc({
  sections,
  active,
}: {
  sections: HubSection[];
  active: boolean;
}) {
  if (!active) return null;

  return (
    <div className="hidden print:block">
      {/* Índice: se deriva de las secciones, así nunca queda desfasado. */}
      <div className="break-after-page">
        <h2 className="border-b-2 border-violet-800/70 pb-2 font-heading text-lg font-bold text-violet-800">
          Contenido
        </h2>
        <ol className="mt-5 space-y-3 text-sm text-neutral-800">
          {sections.map((s, i) => (
            <li key={s.id} className="flex gap-3">
              <span className="w-5 shrink-0 text-right font-mono text-neutral-400">
                {i + 1}
              </span>
              <span>{s.printTitle ?? s.title}</span>
            </li>
          ))}
        </ol>
      </div>

      <div className="space-y-7">
        {sections.map((s, i) => (
          <section key={s.id}>
            <header className="print-heading mb-3 border-b-2 border-violet-800/70 pb-1.5">
              <h2 className="font-heading text-base font-bold text-violet-800">
                {i + 1}. {s.printTitle ?? s.title}
              </h2>
            </header>
            {s.tabs && s.tabs.length > 0 ? (
              <div className="space-y-4">
                {s.tabs.map((t) => (
                  <div key={t.id}>
                    <GroupLabel count={t.count}>{t.label}</GroupLabel>
                    {t.render({ query: "", forPrint: true })}
                  </div>
                ))}
              </div>
            ) : (
              s.render?.({ query: "", forPrint: true })
            )}
          </section>
        ))}
      </div>
    </div>
  );
}
