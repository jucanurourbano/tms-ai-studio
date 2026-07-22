"use client";

import { Menu } from "lucide-react";
import Image from "next/image";
import { useState } from "react";

import { AppSidebar } from "@/components/app-sidebar";
import { cn } from "@/lib/utils";

/**
 * Estructura de la app: sidebar fija en escritorio (md+) y drawer con hamburguesa
 * en móvil/tablet. Mantiene `#app-scroll` como contenedor scrolleable (scrollspy,
 * back-to-top). El drawer se cierra al navegar.
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  const [drawerOpen, setDrawerOpen] = useState(false);

  return (
    <div className="app-root flex h-screen">
      {/* Sidebar de escritorio */}
      <div className="hidden md:flex print:hidden">
        <AppSidebar />
      </div>

      {/* Drawer móvil */}
      <div
        className={cn(
          "fixed inset-0 z-40 md:hidden print:hidden",
          drawerOpen ? "pointer-events-auto" : "pointer-events-none",
        )}
        aria-hidden={!drawerOpen}
      >
        <button
          type="button"
          tabIndex={drawerOpen ? 0 : -1}
          aria-label="Cerrar menú"
          onClick={() => setDrawerOpen(false)}
          className={cn(
            "absolute inset-0 bg-black/40 transition-opacity duration-300",
            drawerOpen ? "opacity-100" : "opacity-0",
          )}
        />
        <div
          className={cn(
            "absolute inset-y-0 left-0 w-64 shadow-xl transition-transform duration-300 ease-in-out",
            drawerOpen ? "translate-x-0" : "-translate-x-full",
          )}
        >
          <AppSidebar forceExpanded onNavigate={() => setDrawerOpen(false)} />
        </div>
      </div>

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Barra superior móvil con hamburguesa */}
        <div className="brand-gradient flex items-center gap-3 px-3 py-2.5 text-white md:hidden print:hidden">
          <button
            type="button"
            onClick={() => setDrawerOpen(true)}
            aria-label="Abrir menú"
            className="rounded-md p-1 transition-colors hover:bg-white/15"
          >
            <Menu className="h-5 w-5" />
          </button>
          <Image
            src="/logo-urbano.png"
            alt="Urbano"
            width={24}
            height={24}
            className="rounded ring-1 ring-white/30"
          />
          <span className="font-heading text-sm font-semibold">TMS AI Studio</span>
        </div>

        <main
          id="app-scroll"
          className="relative flex-1 overflow-y-auto scroll-smooth"
        >
          {children}
        </main>
      </div>
    </div>
  );
}
