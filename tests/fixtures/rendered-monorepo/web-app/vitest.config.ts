import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(import.meta.dirname, "src") },
  },
  test: {
    environment: "jsdom",
    coverage: {
      provider: "v8",
      include: ["src/**/*.{ts,tsx}"],
      // Entry points wire the app together and are covered by running it, not
      // by a unit test. Counting them just moves the number without adding a
      // check — which is the thing DES §11 warns about.
      exclude: ["src/**/*.test.{ts,tsx}", "src/main.tsx", "src/app/layout.tsx"],
      reportsDirectory: "coverage",
    },
  },
});
