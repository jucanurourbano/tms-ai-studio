import { describe, expect, it } from "vitest";

import { flatAgentsForModules, navForModules } from "@/lib/isdf";
import { canAccess, isReadOnly } from "@/lib/permissions";
import type { EffectiveModules } from "@/lib/types/auth";

describe("canAccess", () => {
  it("full cubre read, read no cubre full", () => {
    const modules: EffectiveModules = { ef: "full", scrum: "read" };
    expect(canAccess(modules, "ef", "read")).toBe(true);
    expect(canAccess(modules, "ef", "full")).toBe(true);
    expect(canAccess(modules, "scrum", "read")).toBe(true);
    expect(canAccess(modules, "scrum", "full")).toBe(false);
  });

  it("un módulo ausente no concede nada", () => {
    expect(canAccess({ ef: "full" }, "arquitectura")).toBe(false);
    expect(canAccess({}, "ef")).toBe(false);
    expect(canAccess(undefined, "ef")).toBe(false);
  });

  it("read es el nivel exigido por defecto", () => {
    expect(canAccess({ scrum: "read" }, "scrum")).toBe(true);
  });
});

describe("isReadOnly", () => {
  it("distingue solo-lectura de edición y de sin acceso", () => {
    const modules: EffectiveModules = { ef: "read", scrum: "full" };
    expect(isReadOnly(modules, "ef")).toBe(true);
    expect(isReadOnly(modules, "scrum")).toBe(false);
    // Sin acceso no es "solo lectura": no se ve en absoluto.
    expect(isReadOnly(modules, "arquitectura")).toBe(false);
  });
});

describe("navForModules", () => {
  it("oculta los módulos sin acceso y las fases que quedan vacías", () => {
    // Perfil `procesos`: solo EF.
    const nav = navForModules({ ef: "full" });
    expect(nav).toHaveLength(1);
    expect(nav[0].phase).toBe("Especificar");
    expect(nav[0].agents.map((a) => a.module)).toEqual(["ef"]);
  });

  it("mantiene visibles los agentes aún no implementados si hay permiso", () => {
    // Perfil `developer`: construcción en full (agentes "pronto") + lecturas.
    const nav = navForModules({
      api: "full",
      backend: "full",
      frontend: "full",
      arquitectura: "read",
      scrum: "read",
    });
    const fases = nav.map((p) => p.phase);
    expect(fases).toEqual(["Diseñar", "Construir", "Gestionar"]);

    const construir = nav.find((p) => p.phase === "Construir")!;
    expect(construir.agents.map((a) => a.module)).toEqual([
      "api",
      "backend",
      "frontend",
    ]);
    // Visible pero deshabilitado: tiene permiso, el agente no existe todavía.
    expect(construir.agents.every((a) => a.enabled === false)).toBe(true);

    // "Diseñar" incluye BD, y sin permiso sobre `bd` no debe aparecer.
    const disenar = nav.find((p) => p.phase === "Diseñar")!;
    expect(disenar.agents.map((a) => a.module)).toEqual(["arquitectura"]);
  });

  it("sin permisos no muestra ninguna fase", () => {
    expect(navForModules({})).toEqual([]);
    expect(flatAgentsForModules({})).toEqual([]);
  });

  it("el perfil qa solo ve Scrum", () => {
    const agents = flatAgentsForModules({ qa: "full", scrum: "read" });
    expect(agents.map((a) => a.module)).toEqual(["qa", "scrum"]);
  });
});
