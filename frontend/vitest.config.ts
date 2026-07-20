import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

// Config mínima: tests de lógica pura (helpers de formato/filtro). No requiere
// jsdom. Resuelve el alias "@" para que coincida con tsconfig/Next.
export default defineConfig({
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  test: {
    include: ["src/**/*.test.ts"],
  },
});
